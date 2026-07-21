# Mypy Strict Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Close #39, #41, and #42 by making the entire repository pass strict mypy and enabling the existing CI type-check gate.

**Architecture:** Keep production behavior unchanged. Move reusable test doubles into `tests/fakes.py`, keep pytest fixtures in `tests/conftest.py`, add precise annotations throughout tests, and use narrow `cast(...)` calls only where a fake crosses a production attribute typed as a concrete implementation.

**Tech Stack:** Python 3.12, pytest 9.1.1, mypy 2.3.0, Ruff 0.15.22, GitHub Actions/Aviato reusable CI.

## Global Constraints

- Preserve all 223 existing tests and their assertions.
- Do not add a `tests.*` mypy override, package exclusion, broad `ignore_errors`, or unscoped `# type: ignore`.
- Do not change public runtime behavior to accommodate test doubles.
- `mypy --strict src` must remain clean throughout.
- The final CI command remains `python -m mypy --strict .` and is enabled with `run-typecheck: true`.

---

### Task 1: Shared Typed Test Doubles

**Files:**
- Create: `tests/fakes.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_status_server.py`
- Test: `tests/test_panel_status.py`

**Interfaces:**
- Produces: `FakeReader.read(int) -> bytes`, `FakeWriter.write(bytes) -> None`, `FakePanelConnection.send_command(str, **Any) -> Any`, `MinimalPanel.connect(...) -> None`, and `cast_transport(T) -> DMPTransport`.
- Consumes: `DMPTransport`, `DMPProtocol`, and asyncio stream surfaces from `src/pydmp`.

- [x] **Step 1: Record the failing shared-helper diagnostics**

Run: `.venv/bin/python -m mypy --strict src tests/conftest.py tests/test_status_server.py tests/test_panel_status.py`

Expected: FAIL with missing annotations, incompatible fake assignments, stale ignores, and reader/writer argument errors.

- [x] **Step 2: Create the typed helper module**

Add reusable doubles with fully typed state and methods. The central boundary helper is:

```python
from typing import TypeVar, cast

from pydmp.transport import DMPTransport

T = TypeVar("T")


def cast_transport(fake: T) -> DMPTransport:
    """Cast a structurally compatible test transport at an injection boundary."""
    return cast(DMPTransport, fake)
```

Move the existing reusable reader, writer, panel-connection, config factory support, and minimal CLI panel classes from `tests/conftest.py` into this module. Keep their behavior identical while replacing bare containers such as `list[tuple[str, dict]]` with `list[tuple[str, dict[str, Any]]]`.

- [x] **Step 3: Keep fixture discovery in conftest**

Import the shared helpers into `tests/conftest.py` and retain only pytest fixture definitions there. Give fixtures public pytest types and concrete callable returns:

```python
@pytest.fixture
def cli_cfg(tmp_path: Path) -> Callable[..., Path]:
    def _make(*, top_level: bool = False, port: int = 2011, timeout: float = 1) -> Path:
        path = tmp_path / "cfg.yaml"
        prefix = "" if top_level else "panel:\n  "
        separator = "\n" if top_level else "\n  "
        path.write_text(
            prefix
            + separator.join(
                ("host: h", "account: '1'", "remote_key: 'K'", f"port: {port}", f"timeout: {timeout}")
            )
            + "\n"
        )
        return path

    return _make
```

- [x] **Step 4: Adopt shared doubles in the two representative tests**

Replace local reader/writer or connection duplicates with imports from `tests.fakes`. Annotate callbacks and pytest parameters, and replace fake-to-concrete assignment ignores with `cast_transport(fake)`.

- [x] **Step 5: Verify the shared helper slice**

Run: `.venv/bin/python -m mypy --strict src tests/fakes.py tests/conftest.py tests/test_status_server.py tests/test_panel_status.py`

Expected: `Success: no issues found in 26 source files`.

Run: `.venv/bin/python -m pytest --no-cov tests/test_status_server.py tests/test_panel_status.py`

Expected: 29 tests pass.

- [x] **Step 6: Commit**

```bash
git add tests/fakes.py tests/conftest.py tests/test_status_server.py tests/test_panel_status.py
git commit -m "test: add typed shared fakes"
```

### Task 2: Protocol, Crypto, and Parser Tests

**Files:**
- Modify: `tests/test_command_lengths.py`
- Modify: `tests/test_crypto.py`
- Modify: `tests/test_crypto_edges.py`
- Modify: `tests/test_protocol.py`
- Modify: `tests/test_protocol_edges.py`
- Modify: `tests/test_status_parser.py`
- Modify: `tests/test_users_profiles.py`

**Interfaces:**
- Consumes: `DMPProtocol`, `DMPCrypto`, `S3Message`, `DMPEvent`, and pytest parameter values.
- Produces: fully annotated pure unit tests without new shared runtime helpers.

- [x] **Step 1: Capture the failing pure-unit slice**

Run: `.venv/bin/python -m mypy --strict src tests/test_command_lengths.py tests/test_crypto.py tests/test_crypto_edges.py tests/test_protocol.py tests/test_protocol_edges.py tests/test_status_parser.py tests/test_users_profiles.py`

Expected: FAIL with 42 errors dominated by `no-untyped-def`, plus generic `dict`/`Callable` and one parser case-table mismatch.

- [x] **Step 2: Annotate tests and parametrized values**

Add `-> None` to tests and concrete parameter types. Use typed generic containers, for example:

```python
def test_command_payloads_and_lengths(
    cmd: str,
    kwargs: dict[str, str],
    expected: str,
) -> None:
    encoded = _prot().encode_command(cmd, **kwargs)
    assert encoded.decode("utf-8") == expected
```

Use `pytest.MonkeyPatch`, `pytest.LogCaptureFixture`, and `object` or the exact protocol response type for parametrized inputs instead of leaving parameters untyped.

- [x] **Step 3: Type the parser case table**

Define a checker alias and make the no-message case explicit rather than forcing `None` into an `S3Message` tuple:

```python
EventCheck = Callable[[DMPEvent], None]
ParserCase = tuple[str, S3Message | None, DMPEventType | None, EventCheck | None]
```

Annotate every checker as `(evt: DMPEvent) -> None` and the parametrized test with the four exact alias members.

- [x] **Step 4: Verify the pure-unit slice**

Run: `.venv/bin/python -m mypy --strict src tests/test_command_lengths.py tests/test_crypto.py tests/test_crypto_edges.py tests/test_protocol.py tests/test_protocol_edges.py tests/test_status_parser.py tests/test_users_profiles.py`

Expected: `Success: no issues found in 29 source files`.

Run: `.venv/bin/python -m pytest --no-cov tests/test_command_lengths.py tests/test_crypto.py tests/test_crypto_edges.py tests/test_protocol.py tests/test_protocol_edges.py tests/test_status_parser.py tests/test_users_profiles.py`

Expected: 68 tests pass.

- [x] **Step 5: Commit**

```bash
git add tests/test_command_lengths.py tests/test_crypto.py tests/test_crypto_edges.py tests/test_protocol.py tests/test_protocol_edges.py tests/test_status_parser.py tests/test_users_profiles.py
git commit -m "test: type protocol and parser coverage"
```

### Task 3: Transport and Panel Tests

**Files:**
- Modify: `tests/test_transport.py`
- Modify: `tests/test_transport_sync.py`
- Modify: `tests/test_panel_connection.py`
- Modify: `tests/test_panel_integration.py`
- Modify: `tests/test_panel_arming.py`
- Modify: `tests/test_panel_outputs.py`
- Modify: `tests/test_panel_sync.py`

**Interfaces:**
- Consumes: shared fakes from `tests.fakes`, `DMPPanel`, `DMPPanelSync`, `DMPTransport`, and `DMPTransportSync`.
- Produces: typed transport/panel setup with no optional-attribute monkeypatching or mismatched ignore codes.

- [x] **Step 1: Capture the failing transport/panel slice**

Run: `.venv/bin/python -m mypy --strict src tests/test_transport.py tests/test_transport_sync.py tests/test_panel_connection.py tests/test_panel_integration.py tests/test_panel_arming.py tests/test_panel_outputs.py tests/test_panel_sync.py`

Expected: FAIL with missing definitions plus assignment, union-attribute, method-assignment, and stale-ignore diagnostics.

- [x] **Step 2: Replace duplicated general-purpose fakes**

Import reusable doubles from `tests.fakes`. Keep local scripted fakes only when their response behavior is unique to one test file, and fully annotate those classes. Use `cast_transport(...)` for `_connection` assignments and `cast(DMPProtocol, fake_protocol)` for protocol injection.

- [x] **Step 3: Remove optional method monkeypatching**

Create a typed fake before assigning it, keep a direct local reference, and assert or script through that reference:

```python
connection = FakePanelConnection(["ACK"])
panel._connection = cast_transport(connection)
assert await panel._send_command("!H") == "ACK"
assert connection.calls == [("!H", {})]
```

Do not assign a replacement method through `panel._connection`, whose declared type is optional.

- [x] **Step 4: Annotate pytest surfaces and sync return values**

Add precise types for monkeypatch fixtures, parameter values, fake coroutine methods, and sync wrapper stubs. Use `Coroutine[Any, Any, T]` only where a sync runner consumes an arbitrary coroutine; otherwise use the concrete awaited return type.

- [x] **Step 5: Verify the transport/panel slice**

Run: `.venv/bin/python -m mypy --strict src tests/fakes.py tests/test_transport.py tests/test_transport_sync.py tests/test_panel_connection.py tests/test_panel_integration.py tests/test_panel_arming.py tests/test_panel_outputs.py tests/test_panel_sync.py`

Expected: `Success: no issues found in 30 source files`.

Run: `.venv/bin/python -m pytest --no-cov tests/test_transport.py tests/test_transport_sync.py tests/test_panel_connection.py tests/test_panel_integration.py tests/test_panel_arming.py tests/test_panel_outputs.py tests/test_panel_sync.py`

Expected: 51 tests pass.

- [x] **Step 6: Commit**

```bash
git add tests/fakes.py tests/test_transport.py tests/test_transport_sync.py tests/test_panel_connection.py tests/test_panel_integration.py tests/test_panel_arming.py tests/test_panel_outputs.py tests/test_panel_sync.py
git commit -m "test: type transport and panel coverage"
```

### Task 4: Entity Tests

**Files:**
- Modify: `tests/test_entities.py`

**Interfaces:**
- Consumes: `Area`, `Zone`, `Output`, their sync wrappers, and `FakePanelConnection`.
- Produces: typed entity class/instance parameter matrices and typed sync runner behavior.

- [x] **Step 1: Capture entity diagnostics**

Run: `.venv/bin/python -m mypy --strict src tests/test_entities.py`

Expected: FAIL with 49 errors.

- [x] **Step 2: Type the fake panel boundary**

Annotate call records as `list[tuple[str, dict[str, Any]]]`, coroutine methods as `-> str`, and the sync runner with a generic return type:

```python
T = TypeVar("T")


class _SyncPanel:
    def _run(self, coro: Coroutine[Any, Any, T]) -> T:
        return asyncio.run(coro)
```

- [x] **Step 3: Type parametrized class matrices**

Use unions of `type[Area]`, `type[Zone]`, and `type[Output]` for constructors and matching sync-wrapper types. Where the union cannot preserve a constructor relationship, define a small typed factory callable rather than reverting to untyped parameters.

- [x] **Step 4: Verify entity tests**

Run: `.venv/bin/python -m mypy --strict src tests/test_entities.py`

Expected: `Success: no issues found in 23 source files`.

Run: `.venv/bin/python -m pytest --no-cov tests/test_entities.py`

Expected: 22 tests pass.

- [x] **Step 5: Commit**

```bash
git add tests/test_entities.py
git commit -m "test: type entity coverage"
```

### Task 5: CLI Tests

**Files:**
- Modify: `tests/test_cli_helpers.py`
- Modify: `tests/test_cli_json.py`
- Modify: `tests/test_cli_listen.py`
- Modify: `tests/test_cli_panel_wiring.py`
- Modify: `tests/test_cli_text_and_config.py`
- Modify: `tests/test_cli_text_tables.py`
- Modify: `tests/test_cli_version.py`
- Modify: `tests/test_cli_zones_outputs.py`

**Interfaces:**
- Consumes: `click.testing.CliRunner`, `pytest.MonkeyPatch`, the `cli_cfg` callable fixture, `MinimalPanel`, and typed domain response models.
- Produces: strictly typed CLI fakes, command matrices, and callbacks without relying on module-private re-exports.

- [x] **Step 1: Capture the failing CLI slice**

Run: `.venv/bin/python -m mypy --strict src tests/test_cli_helpers.py tests/test_cli_json.py tests/test_cli_listen.py tests/test_cli_panel_wiring.py tests/test_cli_text_and_config.py tests/test_cli_text_tables.py tests/test_cli_version.py tests/test_cli_zones_outputs.py`

Expected: FAIL with missing definitions, untyped fake calls, and private-module attribute diagnostics.

- [x] **Step 2: Annotate fixtures, commands, and fakes**

Use `pytest.MonkeyPatch`, `Path`, `Callable[..., Path]`, `click.Command`, and exact parameter scalars. Subclass `MinimalPanel` for command-specific async behavior and give every override a concrete return type.

- [x] **Step 3: Correct import and monkeypatch boundaries**

Import `UserCode` and `UserProfile` from their defining `pydmp.user` and `pydmp.profile` modules. Patch asyncio through the standard-library module or use a typed namespace object rather than relying on `pydmp.cli` to export its private import.

- [x] **Step 4: Remove invalid-call ignores deliberately**

For the `_fmt_ddmmyy(None)` negative test, retain only the exact strict diagnostic required to exercise the invalid runtime input:

```python
assert cli._fmt_ddmmyy(None) == ""  # type: ignore[arg-type]
```

If mypy 2.3.0 reports that ignore as unused because the helper now accepts `None`, remove it.

- [x] **Step 5: Verify the CLI slice**

Run: `.venv/bin/python -m mypy --strict src tests/test_cli_helpers.py tests/test_cli_json.py tests/test_cli_listen.py tests/test_cli_panel_wiring.py tests/test_cli_text_and_config.py tests/test_cli_text_tables.py tests/test_cli_version.py tests/test_cli_zones_outputs.py`

Expected: `Success: no issues found in 30 source files`.

Run: `.venv/bin/python -m pytest --no-cov tests/test_cli_helpers.py tests/test_cli_json.py tests/test_cli_listen.py tests/test_cli_panel_wiring.py tests/test_cli_text_and_config.py tests/test_cli_text_tables.py tests/test_cli_version.py tests/test_cli_zones_outputs.py`

Expected: 52 tests pass.

- [x] **Step 6: Commit**

```bash
git add tests/test_cli_helpers.py tests/test_cli_json.py tests/test_cli_listen.py tests/test_cli_panel_wiring.py tests/test_cli_text_and_config.py tests/test_cli_text_tables.py tests/test_cli_version.py tests/test_cli_zones_outputs.py
git commit -m "test: type CLI coverage"
```

### Task 6: Repository-Wide Strict Gate

**Files:**
- Modify: `.github/aviato.yml`
- Modify: `.github/workflows/aviato-ci.yml`
- Modify: Aviato integrity headers in `.editorconfig`, `.github/workflows/aviato-docs.yml`, `.github/workflows/aviato-drift.yml`, `mypy.ini`, `requirements-docs.txt`, and `ruff.toml`
- Modify: `docs/superpowers/plans/2026-07-20-mypy-strict-cleanup.md`

**Interfaces:**
- Consumes: the existing reusable workflow input `run-typecheck` and configured `typecheck-command`.
- Produces: required repository-wide strict type checking in CI.

- [x] **Step 1: Verify the repository gate is red before the final residual sweep**

Run: `.venv/bin/python -m mypy --strict .`

Expected: any remaining diagnostics are limited to files touched in Tasks 1-5; fix each at its source and rerun until the command succeeds.

- [x] **Step 2: Enable CI type checking from the managed source of truth**

Change `.github/aviato.yml` exactly:

```yaml
  typecheck-command: python -m mypy --strict .
  run-typecheck: 'true'
```

Run the pinned Aviato 0.6.1 `sync` command against the worktree. Confirm the rendered `.github/workflows/aviato-ci.yml` contains `run-typecheck: true` and all managed artifact input hashes are refreshed together.

- [x] **Step 3: Run all local release gates**

Run: `.venv/bin/python -m mypy --strict .`

Expected: `Success: no issues found in 51 source files`.

Run: `.venv/bin/python -m ruff check .`

Expected: `All checks passed!`.

Run: `.venv/bin/python -m pytest --cov --cov-report=term-missing`

Expected: 223 tests pass and total coverage remains at least 80%.

Run: `.venv/bin/python -m build`

Expected: source distribution and wheel build successfully.

- [x] **Step 4: Confirm issue criteria and repository state**

Run: `git diff origin/main --check`

Expected: no whitespace errors.

Run: `git status --short`

Expected: only the final intended CI/plan edits are uncommitted before the final commit.

- [x] **Step 5: Commit**

```bash
git add .github/aviato.yml .github/workflows/aviato-ci.yml .github/workflows/aviato-docs.yml .github/workflows/aviato-drift.yml .editorconfig mypy.ini requirements-docs.txt ruff.toml docs/superpowers/plans/2026-07-20-mypy-strict-cleanup.md docs/superpowers/specs/2026-07-20-mypy-strict-cleanup-design.md
git commit -m "ci: enforce repository-wide strict typing"
```
