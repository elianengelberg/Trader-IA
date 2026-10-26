"""D3 (mission v3): SIGTERM must reach the application's shutdown even with a dashboard open.

uvicorn runs the application's shutdown (``AppState.shutdown``: stop the sessions, flush,
record, release the lease and the session lock) only after every open HTTP response has
finished, and with ``timeout_graceful_shutdown`` unset it waits for ever. The dashboard's event
stream (``/api/stream``) never finishes on its own. Measured on the real server
(reproduction/d3): with one stream open, SIGTERM did nothing for 120 s, then SIGKILL; nothing
was recorded. ``tia.api.main.run`` now bounds that wait (``GRACEFUL_SHUTDOWN_SECONDS``).

These run the real uvicorn server in a subprocess, with its own signal handling, over the
fake public feed (no network), and send it a real SIGTERM. The test talks to it over loopback
with ``http.client``: the suite's network guard replaces httpx's real transports, and is left
as it is (this is a server the test itself started, on 127.0.0.1).
"""

from __future__ import annotations

import http.client
import json
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]

LAUNCHER = r"""
import os, sys
root, url, port, graceful = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
sys.path[:0] = [root, os.path.join(root, "packages/tia/src")]
import uvicorn
import tia.data.providers.binance_public as binance_public
from tests.integration.test_live_api import _FakePublicFeed
from tia.api.app import create_app
from tia.api.main import graceful_shutdown_seconds
from tia.core.config import Environment, LiveConfig, settings_for_env
binance_public.BinancePublicProvider = _FakePublicFeed
live = LiveConfig().model_copy(update={"market_stream": False, "charge_funding": False})
settings = settings_for_env(Environment.TESTING).model_copy(update={"database_url": url, "live": live})
kwargs = {} if graceful == "unbounded" else {"timeout_graceful_shutdown": graceful_shutdown_seconds()}
uvicorn.run(create_app(settings), host="127.0.0.1", port=port, reload=False, log_config=None, **kwargs)
"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _request(port: int, method: str, path: str, *, body: dict[str, Any] | None = None,
             cookie: str = "") -> tuple[int, str, bytes]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    try:
        headers = {"Content-Type": "application/json"} if body is not None else {}
        if cookie:
            headers["Cookie"] = cookie
        conn.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
        r = conn.getresponse()
        return r.status, r.getheader("Set-Cookie") or "", r.read()
    finally:
        conn.close()


def _serve(tmp_path: Path, *, graceful: str, env_extra: dict[str, str] | None = None) -> tuple[subprocess.Popen[bytes], int, Path]:
    db = tmp_path / "shutdown.db"
    port = _free_port()
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "TZ")}
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "TIA_DEMO_USER": "live-operator", "TIA_DEMO_PASSWORD": "live-password-not-a-secret",
                "HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9", "NO_PROXY": "127.0.0.1,localhost",
                **(env_extra or {})})
    log = open(tmp_path / "server.log", "wb")  # noqa: SIM115 - the server process owns it until it ends
    proc = subprocess.Popen([sys.executable, "-c", LAUNCHER, str(ROOT), f"sqlite+aiosqlite:///{db}", str(port), graceful],  # noqa: S603
                            cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            if _request(port, "GET", "/api/health")[0] == 200:
                break
        except OSError:
            time.sleep(0.1)
    else:
        proc.kill()
        raise AssertionError("the server did not come up")
    return proc, port, db


def _start_session_and_open_stream(port: int) -> None:
    status, set_cookie, _ = _request(port, "POST", "/api/auth/login",
                                     body={"username": "live-operator", "password": "live-password-not-a-secret"})
    assert status == 200
    cookie = set_cookie.split(";", 1)[0]
    assert _request(port, "POST", "/api/live/paper-start", cookie=cookie)[0] == 200
    opened = threading.Event()

    def read() -> None:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=None)
        try:
            conn.request("GET", "/api/stream", headers={"Cookie": cookie})
            r = conn.getresponse()
            if r.status == 200:
                opened.set()
                while r.read1(1024):
                    pass
        except OSError:
            pass
        finally:
            conn.close()

    threading.Thread(target=read, daemon=True).start()
    assert opened.wait(10), "the event stream did not open"
    time.sleep(1.0)


def _runs(db: Path) -> list[dict[str, Any]]:
    con = sqlite3.connect(db)
    try:
        rows = con.execute("SELECT run_id, mode, notes FROM runs").fetchall()
    finally:
        con.close()
    out = []
    for run_id, mode, notes in rows:
        doc = json.loads(notes or "{}")
        out.append({"run_id": run_id, "mode": mode, "persistence": (doc.get("persistence") or {}).get("status"),
                    "heartbeat": doc.get("heartbeat_at")})
    return out


def test_sigterm_with_the_dashboard_stream_open_runs_the_shutdown(tmp_path: Path) -> None:
    proc, port, db = _serve(tmp_path, graceful="bounded", env_extra={"TIA_GRACEFUL_SHUTDOWN_SECONDS": "2"})
    try:
        _start_session_and_open_stream(port)
        t0 = time.monotonic()
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=30)
        took = time.monotonic() - t0
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    assert took < 15, f"the stop took {took:.1f}s"
    [run] = [r for r in _runs(db) if r["mode"] == "paper-live"]
    assert run["persistence"] == "complete", run
    assert run["heartbeat"] is None, "the lease was released for the next boot"
    log = (tmp_path / "server.log").read_text(errors="replace")
    assert "session_lock_released" in log


def test_control_without_the_bound_the_same_stop_does_not_happen(tmp_path: Path) -> None:
    """The failure mode the bound removes, shown on the same harness (kept short: 8 s)."""
    proc, port, db = _serve(tmp_path, graceful="unbounded")
    try:
        _start_session_and_open_stream(port)
        proc.send_signal(signal.SIGTERM)
        with pytest.raises(subprocess.TimeoutExpired):
            proc.wait(timeout=8)
    finally:
        proc.kill()
        proc.wait()
    [run] = [r for r in _runs(db) if r["mode"] == "paper-live"]
    assert run["persistence"] is None, "no stop record: the shutdown never ran"


def test_run_bounds_the_graceful_shutdown(monkeypatch: pytest.MonkeyPatch) -> None:
    import uvicorn

    from tia.api import main

    seen: dict[str, Any] = {}
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: seen.update(k))
    monkeypatch.delenv("TIA_GRACEFUL_SHUTDOWN_SECONDS", raising=False)
    main.run()
    assert seen["timeout_graceful_shutdown"] == main.GRACEFUL_SHUTDOWN_SECONDS == 5.0
    monkeypatch.setenv("TIA_GRACEFUL_SHUTDOWN_SECONDS", "12")
    main.run()
    assert seen["timeout_graceful_shutdown"] == 12.0
    for bad in ("x", "-3"):
        monkeypatch.setenv("TIA_GRACEFUL_SHUTDOWN_SECONDS", bad)
        main.run()
        assert seen["timeout_graceful_shutdown"] == 5.0
