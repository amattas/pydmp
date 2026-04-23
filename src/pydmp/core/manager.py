"""Queue-driven command/session manager for one panel endpoint.

This file is the traffic cop for the new core.

It exists to solve three practical problems:

1. only one command should be in flight on a panel session at a time
2. callers still want a simple "submit and await the result" API
3. idle sessions should close themselves instead of lingering forever

The manager does not know protocol details. Session setup, teardown, and wire
exchange rules stay inside the selected session profile.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from .errors import (
    CommandSessionError,
    SessionClosedError,
    SessionProtocolError,
    TransactionParseError,
)
from .models import PanelEndpoint, SessionState, Transaction, payload_required
from .sessions import SessionProfile, SessionProfileBlankV2
from .transport import PanelTransport, TransportProtocol


@dataclass(slots=True)
class _QueuedTransaction:
    """Small internal record pairing a transaction with its waiting future."""

    transaction: Transaction
    future: asyncio.Future[Transaction]


_QUEUE_STOP = object()


class CommandSessionManager:
    """Run transactions one at a time through one short-lived panel session.

    Callers hand the manager ready-to-run transactions.
    The manager opens a session when needed, runs queued work in order, and
    closes the session again after the queue stays idle long enough.
    """

    def __init__(
        self,
        endpoint: PanelEndpoint,
        session_profile: SessionProfile | None = None,
        *,
        transport_factory: Callable[[PanelEndpoint], TransportProtocol] = PanelTransport,
    ) -> None:
        # Keep the constructor light: store the panel details, choose a session
        # profile, and create the transport object that will be reused between
        # queued commands.
        self._endpoint = endpoint
        self._session_profile = session_profile or SessionProfileBlankV2()
        self._transport_factory = transport_factory
        self._transport = transport_factory(endpoint)
        self._session_state: SessionState | None = None
        self._queue: asyncio.Queue[_QueuedTransaction | object] = asyncio.Queue()
        self._worker_task: asyncio.Task[None] | None = None
        self._idle_close_task: asyncio.Task[None] | None = None
        self._closed = False

    @property
    def session_is_open(self) -> bool:
        """Return True when a usable session is already open."""
        return self._session_state is not None and self._transport.is_connected

    async def submit(self, transaction: Transaction) -> Transaction:
        """Queue one transaction and wait for the completed result.

        This is the normal entry point.
        Callers do not need to think about worker tasks or queue plumbing.
        """
        if self._closed:
            raise SessionClosedError("CommandSessionManager is closed")

        # Any new work means the session should stay alive for now.
        self._cancel_idle_close()
        self._ensure_worker()

        loop = asyncio.get_running_loop()
        future: asyncio.Future[Transaction] = loop.create_future()
        await self._queue.put(_QueuedTransaction(transaction=transaction, future=future))
        return await future

    async def execute(
        self,
        body: bytes | str,
        *,
        completion=None,
        label: str | None = None,
    ) -> Transaction:
        """Build and submit a one-off transaction without making a subclass."""
        transaction = Transaction(body=body, completion=completion or payload_required(), label=label)
        return await self.submit(transaction)

    async def close(self) -> None:
        """Close the manager, fail queued work, and shut down the session."""
        if self._closed:
            return

        self._closed = True
        self._cancel_idle_close()
        await self._drain_queue(SessionClosedError("CommandSessionManager is closed"))

        if self._worker_task is not None:
            await self._queue.put(_QUEUE_STOP)
            await self._worker_task
            self._worker_task = None

        await self._close_active_session()

    def _ensure_worker(self) -> None:
        """Start the background queue worker on first use."""
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._run_queue())

    async def _run_queue(self) -> None:
        """Process queued transactions until the manager is stopped.

        The flow is intentionally simple:

        - wait for one queued item
        - make sure a session is open
        - let the selected session profile execute the transaction
        - parse the result
        - wake the waiting caller

        If anything session-related fails, the queue is drained and the active
        session is thrown away. That keeps later callers from inheriting a
        half-broken session.
        """
        while True:
            item = await self._queue.get()
            if item is _QUEUE_STOP:
                return

            queued = cast(_QueuedTransaction, item)

            try:
                # The session profile owns authentication and wire formatting.
                await self._ensure_session_open()
                if self._session_state is None:
                    raise SessionProtocolError("Session state was not initialized")

                completed = await self._session_profile.execute(
                    self._endpoint,
                    self._transport,
                    self._session_state,
                    queued.transaction,
                )
            except CommandSessionError as err:
                if not queued.future.done():
                    queued.future.set_exception(err)
                await self._drain_queue(err)
                await self._close_active_session()
                continue
            except Exception as err:
                session_error = SessionProtocolError(str(err))
                if not queued.future.done():
                    queued.future.set_exception(session_error)
                await self._drain_queue(session_error)
                await self._close_active_session()
                continue

            try:
                # Parsing happens after the wire exchange so protocol code and
                # parser code fail independently and produce clearer errors.
                completed.apply_parser()
            except Exception as err:
                parse_error = TransactionParseError(f"Failed to parse transaction reply for {completed.label or completed.body!r}: {err}")
                if not queued.future.done():
                    queued.future.set_exception(parse_error)
                if self._queue.empty():
                    self._schedule_idle_close()
                continue

            if not queued.future.done():
                queued.future.set_result(completed)

            if self._queue.empty():
                self._schedule_idle_close()

    async def _ensure_session_open(self) -> None:
        """Open the transport and session profile if one is not already live."""
        if self.session_is_open:
            return

        await self._transport.connect()
        try:
            self._session_state = await self._session_profile.open(self._endpoint, self._transport)
        except Exception:
            await self._transport.disconnect()
            self._session_state = None
            raise

    def _schedule_idle_close(self) -> None:
        """Arm the delayed idle-close task after the queue drains."""
        self._cancel_idle_close()
        self._idle_close_task = asyncio.create_task(self._idle_close_after_delay())

    def _cancel_idle_close(self) -> None:
        """Cancel any pending idle-close task.

        New work should keep the current session alive instead of racing a
        background shutdown.
        """
        if self._idle_close_task is None:
            return
        if not self._idle_close_task.done():
            self._idle_close_task.cancel()
        self._idle_close_task = None

    async def _idle_close_after_delay(self) -> None:
        """Close the session after the configured idle delay.

        The delay comes from `PanelEndpoint.idle_disconnect_seconds`.
        The notes for this project settled on short-lived sessions so that
        helpers behave predictably and do not hold panel sockets open longer
        than they need to.
        """
        try:
            await asyncio.sleep(self._endpoint.idle_disconnect_seconds)
            if self._queue.empty():
                await self._close_active_session()
        except asyncio.CancelledError:
            return

    async def _drain_queue(self, error: CommandSessionError) -> None:
        """Fail any queued transactions with the same session-level error."""
        while True:
            try:
                item = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                return

            if item is _QUEUE_STOP:
                continue

            queued = cast(_QueuedTransaction, item)
            if not queued.future.done():
                queued.future.set_exception(error)

    async def _close_active_session(self) -> None:
        """Close the current session profile and disconnect the transport.

        This method is intentionally forgiving. Shutdown should not replace the
        original error that caused the session to be discarded.
        """
        state = self._session_state
        self._session_state = None

        if state is not None:
            try:
                await self._session_profile.close(self._endpoint, self._transport, state)
            except Exception:
                pass

        await self._transport.disconnect()
