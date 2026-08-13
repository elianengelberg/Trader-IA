"""Entry point: ``python -m tia.api.main`` or ``uvicorn tia.api.main:app``."""

from __future__ import annotations

import os

from tia.api.app import create_app
from tia.core.config import get_settings

app = create_app(get_settings())


def run() -> None:  # pragma: no cover - process entry point
    import uvicorn

    uvicorn.run(
        "tia.api.main:app",
        host=os.environ.get("TIA_HOST", "127.0.0.1"),
        port=int(os.environ.get("TIA_PORT", "8000")),
        reload=False,
        log_config=None,
    )


if __name__ == "__main__":  # pragma: no cover
    run()
