"""Integration-flavored panel behaviors: keepalive lifecycle, status-server
attach/detach, check_code caching paths, and paginated fetch loops."""

import asyncio

import pytest

from pydmp.const.commands import DMPCommand
from pydmp.const.events import DMPEventType
from pydmp.panel import DMPPanel
from pydmp.protocol import (
    UserCode as ProtoUserCode,
)
from pydmp.protocol import (
    UserCodesResponse,
    UserProfile,
    UserProfilesResponse,
)
from tests.conftest import make_user_code


class _DummyProtocol:
    def encode_command(self, cmd: str, **kwargs) -> bytes:  # noqa: D401
        return b"KA" if cmd == DMPCommand.KEEP_ALIVE.value else b"X"

    def decode_response(self, data: bytes):  # noqa: D401
        return None


class _DummyTransport:
    def __init__(self):
        self.is_connected = True
        self.sent: list[bytes] = []

    async def send_and_receive(self, data: bytes) -> bytes:  # noqa: D401
        self.sent.append(bytes(data))
        return b""  # no response expected


@pytest.mark.asyncio
async def test_keepalive_start_stop():
    # Merge of test_panel_misc.py::test_keepalive_start_stop (task lifecycle)
    # and test_panel_keepalive.py::test_keepalive_start_stop (bytes sent).
    p = DMPPanel()
    p._protocol = _DummyProtocol()  # type: ignore[attr-defined]
    p._connection = _DummyTransport()  # type: ignore[attr-defined]

    await p.start_keepalive(interval=0.01)
    assert p._keepalive_task is not None
    await asyncio.sleep(0.05)

    # ensure at least one KA went out
    assert isinstance(p._connection, _DummyTransport)
    assert len(p._connection.sent) >= 1

    await p.stop_keepalive()
    assert p._keepalive_task is None


@pytest.mark.asyncio
async def test_keepalive_idempotent():
    p = DMPPanel()
    p._protocol = _DummyProtocol()  # type: ignore[attr-defined]
    p._connection = _DummyTransport()  # type: ignore[attr-defined]

    # starting twice should not raise and should keep sending
    await p.start_keepalive(interval=0.01)
    await p.start_keepalive(interval=0.01)
    await asyncio.sleep(0.03)
    await p.stop_keepalive()
    assert isinstance(p._connection, _DummyTransport)
    assert len(p._connection.sent) >= 1


@pytest.mark.asyncio
async def test_attach_detach_status_server(monkeypatch):
    # Merge of test_panel_more.py::test_attach_status_server_idempotence_and_detach_unknown
    # and test_panel_status_server_integration.py::test_attach_detach_status_server:
    # idempotent attach, unknown detach no-op, callback fires and triggers
    # _refresh_user_cache.
    p = DMPPanel()
    refreshed = {"count": 0}

    async def refresh():  # noqa: D401
        refreshed["count"] += 1

    monkeypatch.setattr(p, "_refresh_user_cache", refresh)

    class Srv:
        def __init__(self):
            self._cbs = []

        def register_callback(self, cb):
            self._cbs.append(cb)

        def remove_callback(self, cb):
            if cb in self._cbs:
                self._cbs.remove(cb)

    class _Evt:
        category = DMPEventType.USER_CODES

    monkeypatch.setattr("pydmp.panel.parse_s3_message", lambda msg: _Evt())

    s = Srv()
    p.attach_status_server(s)
    p.attach_status_server(s)  # idempotent
    # Trigger callback
    for cb in list(p._status_callbacks.values()):
        await cb(object())
    assert refreshed["count"] == 1

    # Detach unknown does nothing
    p.detach_status_server(object())
    # Detach registered
    p.detach_status_server(s)
    assert not p._status_callbacks


@pytest.mark.asyncio
async def test_attach_detach_status_server_single_callback_registration(monkeypatch):
    # test_panel_status_server_integration.py::test_attach_detach_status_server:
    # a simpler status-server double that stores a single callback slot rather
    # than a collection, covering the register/remove_callback contract shape.
    p = DMPPanel()
    refreshed = {"ok": False}

    async def fake_refresh():
        refreshed["ok"] = True

    monkeypatch.setattr(p, "_refresh_user_cache", fake_refresh)

    class _Evt:
        category = DMPEventType.USER_CODES

    monkeypatch.setattr("pydmp.panel.parse_s3_message", lambda msg: _Evt())

    class _Srv:
        def __init__(self):
            self.cb = None

        def register_callback(self, cb):
            self.cb = cb

        def remove_callback(self, cb):  # noqa: D401
            if self.cb == cb:
                self.cb = None

    s = _Srv()
    p.attach_status_server(s)
    assert s.cb is not None
    await s.cb(object())
    assert refreshed["ok"] is True
    p.detach_status_server(s)
    assert s.cb is None


@pytest.mark.asyncio
async def test_check_code_refresh(monkeypatch):
    # test_panel_commands.py::test_check_code_refresh: successful refresh.
    p = DMPPanel()
    p._user_cache_by_code = {}
    p._user_cache_by_pin = {}

    async def fake_refresh():
        u = make_user_code(code="1234", pin="1111")
        p._user_cache_by_code = {"1234": u}
        p._user_cache_by_pin = {"1111": u}

    monkeypatch.setattr(p, "_refresh_user_cache", fake_refresh)

    got = await p.check_code("1234", include_pin=True)
    assert got and got.number == "0001"


@pytest.mark.asyncio
async def test_check_code_negative_paths(monkeypatch):
    # test_panel_more.py::test_check_code_negative_paths: no-refresh miss, and
    # a refresh that raises still resolves to None.
    p = DMPPanel()

    # Case 1: refresh_if_missing=False returns None without refresh
    p._user_cache_by_code = {}
    p._user_cache_by_pin = {}
    got = await p.check_code("9999", include_pin=True, refresh_if_missing=False)
    assert got is None

    # Case 2: refresh raises exception then None
    async def bad_refresh():  # noqa: D401
        raise RuntimeError("boom")

    monkeypatch.setattr(p, "_refresh_user_cache", bad_refresh)
    got2 = await p.check_code("9999", include_pin=True, refresh_if_missing=True)
    assert got2 is None


@pytest.mark.asyncio
async def test_check_code_cached_short_circuit_during_concurrent_refresh(monkeypatch):
    # test_panel_more.py::test_refresh_user_cache_no_empty_window (PYDMP-006):
    # a concurrent refresh must never expose an emptied cache to check_code;
    # a cached reader short-circuits to the old entry until the atomic swap.
    p = DMPPanel()
    old = make_user_code()
    new = make_user_code()
    p._user_cache_by_code = {"1234": old}
    p._user_cache_by_pin = {}

    gate = asyncio.Event()

    async def slow_get_user_codes():
        # Mid-refresh the live cache must still expose the old entry
        # (no clear-then-repopulate window).
        assert p._user_cache_by_code.get("1234") is old
        await gate.wait()
        return [new]

    monkeypatch.setattr(p, "get_user_codes", slow_get_user_codes)

    task = asyncio.create_task(p._refresh_user_cache())
    await asyncio.sleep(0)  # let refresh reach the await inside get_user_codes

    # Concurrent reader during the refresh window still resolves the code
    # (cached short-circuit path; no refresh triggered).
    got = await p.check_code("1234", refresh_if_missing=False)
    assert got is old

    gate.set()
    await task
    assert p._user_cache_by_code["1234"] is new


def _uc(num: str) -> ProtoUserCode:
    return ProtoUserCode(
        number=num,
        code="1234",
        pin="",
        profiles=("001", "002", "003", "004"),
        temp_date="010125",
        exp_date="0900",
        name=f"U{num}",
    )


def _prof(num: str) -> UserProfile:
    return UserProfile(
        number=num,
        areas_mask="C3000000",
        access_areas_mask="C3000000",
        output_group="001",
        menu_options="MENUOPTS",
        rearm_delay="005",
        name=f"P{num}",
    )


@pytest.mark.parametrize(
    ("panel_method", "make_page", "response_cls"),
    [
        ("get_user_codes", lambda n: [_uc(n)], UserCodesResponse),
        ("get_user_profiles", lambda n: [_prof(n)], UserProfilesResponse),
    ],
    ids=["user_codes", "user_profiles"],
)
@pytest.mark.asyncio
async def test_get_user_codes_and_profiles_pagination(
    monkeypatch, panel_method, make_page, response_cls
):
    # Merge of test_panel_commands.py::test_get_user_codes_pagination and
    # test_panel_send_sequences.py::test_get_user_profiles_pagination:
    # identical two-page pagination loop, parameterized over entity type.
    p = DMPPanel()

    class _Conn:
        is_connected = True

    p._connection = _Conn()  # type: ignore[attr-defined]

    kwarg_name = "users" if response_cls is UserCodesResponse else "profiles"
    pages = [
        response_cls(**{kwarg_name: make_page("001"), "has_more": True, "last_number": "001"}),
        response_cls(**{kwarg_name: make_page("002"), "has_more": False, "last_number": "002"}),
    ]
    state = {"i": 0}

    async def fake_send(self, command: str, **kwargs):
        i = state["i"]
        state["i"] = min(i + 1, len(pages) - 1)
        return pages[i]

    monkeypatch.setattr(DMPPanel, "_send_command", fake_send)
    results = await getattr(p, panel_method)()
    assert [r.number for r in results] == ["001", "002"]
