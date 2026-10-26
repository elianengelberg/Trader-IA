"""Entry point: ``python -m tia.api.main`` or ``uvicorn tia.api.main:app``."""

from __future__ import annotations

import os

from tia.api.app import create_app
from tia.core.config import get_settings

app = create_app(get_settings())


#: How long a stop waits for open HTTP responses before cancelling them (mission v3, D3).
#: Without a bound uvicorn waits for every one to finish before it runs the application's
#: shutdown, and the dashboard's event stream (``/api/stream``) never finishes: with one
#: browser tab open, SIGTERM did nothing for 120 s and the process had to be SIGKILLed — no
#: flush, no stop record, no lease release (reproduction/d3, b_live_sse). The stream is
#: cancelled after this, and the browser reconnects to the next process on its own.
GRACEFUL_SHUTDOWN_SECONDS = 5.0


def graceful_shutdown_seconds() -> float:
    raw = os.environ.get("TIA_GRACEFUL_SHUTDOWN_SECONDS", "")
    try:
        value = float(raw) if raw else GRACEFUL_SHUTDOWN_SECONDS
    except ValueError:
        return GRACEFUL_SHUTDOWN_SECONDS
    return value if value >= 0 else GRACEFUL_SHUTDOWN_SECONDS


def run() -> None:  # pragma: no cover - process entry point
    import uvicorn

    uvicorn.run(
        "tia.api.main:app",
        host=os.environ.get("TIA_HOST", "127.0.0.1"),
        port=int(os.environ.get("TIA_PORT", "8000")),
        reload=False,
        log_config=None,
        timeout_graceful_shutdown=graceful_shutdown_seconds(),
    )


if __name__ == "__main__":  # pragma: no cover
    run()
