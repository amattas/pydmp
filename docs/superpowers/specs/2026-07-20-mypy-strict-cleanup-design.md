# Mypy Strict Cleanup Design

**Issues:** #39, #41, #42

**Goal:** Make `mypy --strict .` pass for the complete repository and enforce that command in CI without changing PyDMP runtime behavior.

## Current State

The current `origin/main` already passes `mypy --strict src` across 22 source files. The source annotation cleanup originally described by #41 has therefore landed independently. The remaining local baseline is 489 errors across 26 test files, primarily missing annotations on tests and fakes, incompatible assignments of test doubles to concrete internal types, and stale `type: ignore` comments.

The CI workflow already carries `python -m mypy --strict .` as its configured type-check command, but disables the type-check job with `run-typecheck: false`.

## Architecture

Production modules remain unchanged unless repository-wide strict checking exposes a genuine public-export or source typing defect that `mypy --strict src` does not currently detect. Test-only typing support will live in `tests/fakes.py`, separate from pytest fixture discovery in `tests/conftest.py`.

Shared test doubles will expose the smallest structural interfaces needed by tests. Tests that must place a structurally compatible double into a production attribute declared as a concrete class will use an explicit, narrow `cast(...)` at that assignment boundary. Bespoke one-use fakes may remain local when moving them would not remove duplication, but every callable and generic container will be fully annotated.

## Components

### Typed test support

Create `tests/fakes.py` for reusable reader, writer, panel-connection, protocol, transport, and CLI panel surfaces currently duplicated across multiple files. Shared helpers will use concrete return types and typed call records rather than `Any` wherever the tested interface is known.

Keep pytest fixtures in `tests/conftest.py`. The fixture module may import typed helpers from `tests.fakes`, but ordinary tests will import reusable doubles directly from `tests.fakes` instead of importing from `conftest`.

### Test annotations

Annotate every test function, fixture parameter, parametrized value, local callback, and fake method reported by strict mypy. Use pytest's public types such as `pytest.MonkeyPatch`, `pytest.CaptureFixture[str]`, and `pytest.LogCaptureFixture`, plus standard-library types such as `Callable`, `Awaitable`, and `Sequence`.

Replace stale or mismatched ignores with correctly typed code. An ignore may remain only when it covers a deliberate test of an invalid call or an unavoidable third-party typing limitation, and its error code must match the actual strict-mypy diagnostic.

### CI enforcement

Once `mypy --strict .` passes locally, change the owning `.github/aviato.yml` declaration to set `run-typecheck: 'true'`, then regenerate the Aviato-managed workflows so `.github/workflows/aviato-ci.yml` carries `run-typecheck: true` with current integrity markers. Do not add a `tests.*` relaxation because #42 is included in this change and the completed tree will be strict in one pass.

No `types-PyYAML` dependency will be added unless a clean environment reproduces an untyped-import error. PyYAML 6.0.3 in the pinned development environment currently satisfies `mypy --strict src`, so adding an unnecessary stub dependency would create avoidable maintenance.

## Data and Control Flow

Runtime data flow is unchanged. During tests, typed fakes record calls and return scripted values exactly as the existing fakes do. Casts occur only where a test injects a fake through a concrete private production attribute; they do not alter runtime objects.

CI installs `.[dev]`, runs the existing configured strict command over the repository root, and blocks merges when any source or test typing regression is introduced.

## Error Handling

The work will preserve all existing runtime assertions and exception-path coverage. Test annotations must describe existing behavior rather than weaken assertions, skip tests, or silence diagnostics broadly. If strict checking finds an actual unsafe test setup, the setup will be corrected at its source.

## Verification

Implementation follows a red-green sequence around the static-analysis gate:

1. Capture the failing `mypy --strict .` baseline and group diagnostics by file and error code.
2. Fix one coherent test group at a time and rerun strict mypy for that group.
3. Run the affected pytest file after each group to confirm annotations and fake consolidation preserve runtime behavior.
4. Run the full gates: `python -m mypy --strict .`, `python -m ruff check .`, `python -m pytest --cov --cov-report=term-missing`, and `python -m build`.
5. Confirm the workflow enables the configured repository-wide type-check command.

## Completion Criteria

- `mypy --strict src` remains clean.
- `mypy --strict .` reports no errors across source and tests.
- All 223 existing tests pass with no tests removed or skipped to satisfy typing.
- Shared reusable fakes are defined once in `tests/fakes.py` rather than duplicated across test files.
- Broad test-package mypy overrides and exclusions are absent.
- CI runs `python -m mypy --strict .` with `run-typecheck: true`.
- Ruff, package build, and the full coverage-enabled test suite pass.
