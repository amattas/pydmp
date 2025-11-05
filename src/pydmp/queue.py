"""Command queue for rate-limited async operations."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from .const.protocol import RATE_LIMIT_SECONDS
from .protocol import StatusResponse

_LOGGER = logging.getLogger(__name__)


@dataclass
class QueuedCommand:
    """A queued command with result future."""

    command: str
    kwargs: dict[str, Any]
    encrypt_user_code: bool
    user_code: str | None
    result: asyncio.Future[str | StatusResponse | None]


class CommandQueue:
    """Async command queue with rate limiting."""

    def __init__(self, connection: Any, rate_limit: float = RATE_LIMIT_SECONDS):
        """Initialize command queue.

        Args:
            connection: DMPConnection instance
            rate_limit: Minimum seconds between commands
        """
        self._connection = connection
        self._rate_limit = rate_limit
        self._queue: asyncio.Queue[QueuedCommand] = asyncio.Queue()
        self._worker_task: asyncio.Task[None] | None = None
        self._running = False
        self._last_command_time = 0.0

    async def start(self) -> None:
        """Start queue worker."""
        if self._running:
            return

        self._running = True
        self._worker_task = asyncio.create_task(self._worker())
        _LOGGER.debug("Command queue started")

    async def stop(self) -> None:
        """Stop queue worker and wait for pending commands."""
        if not self._running:
            return

        self._running = False

        # Wait for queue to empty
        await self._queue.join()

        # Cancel worker
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        self._worker_task = None
        _LOGGER.debug("Command queue stopped")

    async def enqueue(
        self,
        command: str,
        encrypt_user_code: bool = False,
        user_code: str | None = None,
        **kwargs: Any,
    ) -> str | StatusResponse | None:
        """Enqueue a command for execution.

        Args:
            command: Command to send
            encrypt_user_code: Whether user code should be encrypted
            user_code: User code for encrypted commands
            **kwargs: Command parameters

        Returns:
            Command response

        Raises:
            RuntimeError: If queue is not running
        """
        if not self._running:
            raise RuntimeError("Command queue is not running")

        # Create future for result
        result_future: asyncio.Future[str | StatusResponse | None] = asyncio.Future()

        # Create queued command
        queued_cmd = QueuedCommand(
            command=command,
            kwargs=kwargs,
            encrypt_user_code=encrypt_user_code,
            user_code=user_code,
            result=result_future,
        )

        # Add to queue
        await self._queue.put(queued_cmd)
        _LOGGER.debug(f"Command queued: {command}, queue size: {self._queue.qsize()}")

        # Wait for result
        return await result_future

    async def _worker(self) -> None:
        """Queue worker that processes commands with rate limiting."""
        _LOGGER.debug("Queue worker started")

        while self._running:
            try:
                # Get next command (with timeout to check _running periodically)
                try:
                    cmd = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                # Apply rate limiting
                await self._rate_limit_wait()

                # Execute command
                try:
                    _LOGGER.debug(f"Executing command: {cmd.command}")
                    response = await self._connection.send_command(
                        cmd.command,
                        encrypt_user_code=cmd.encrypt_user_code,
                        user_code=cmd.user_code,
                        **cmd.kwargs,
                    )
                    cmd.result.set_result(response)
                    _LOGGER.debug(f"Command completed: {cmd.command}")

                except Exception as e:
                    _LOGGER.error(f"Command failed: {cmd.command}, error: {e}")
                    cmd.result.set_exception(e)

                finally:
                    self._queue.task_done()
                    self._last_command_time = asyncio.get_event_loop().time()

            except asyncio.CancelledError:
                _LOGGER.debug("Queue worker cancelled")
                break
            except Exception as e:
                _LOGGER.error(f"Unexpected error in queue worker: {e}", exc_info=True)

        _LOGGER.debug("Queue worker stopped")

    async def _rate_limit_wait(self) -> None:
        """Wait for rate limit period if needed."""
        if self._last_command_time == 0.0:
            return

        loop = asyncio.get_event_loop()
        elapsed = loop.time() - self._last_command_time

        if elapsed < self._rate_limit:
            wait_time = self._rate_limit - elapsed
            _LOGGER.debug(f"Rate limiting: waiting {wait_time:.3f}s")
            await asyncio.sleep(wait_time)

    @property
    def queue_size(self) -> int:
        """Get current queue size."""
        return self._queue.qsize()

    @property
    def is_running(self) -> bool:
        """Check if queue worker is running."""
        return self._running
