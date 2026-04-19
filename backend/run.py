"""
Simple script to run the FastAPI server.

Environment variables
---------------------
SQLAGENT_RELOAD   – "1" (default) to enable auto-reload for development.
                    Set to "0" in production.
SQLAGENT_WORKERS  – Number of uvicorn workers (default 1 in dev, 4 in prod).
                    Only used when reload is *off* (multiple workers + reload
                    are incompatible).
PORT              – Port number (default 8001). Azure App Service sets this
                    automatically.
"""
import os

import uvicorn

if __name__ == "__main__":
    _reload = os.environ.get("SQLAGENT_RELOAD", "1").lower() not in (
        "0",
        "false",
        "no",
    )
    _port = int(os.environ.get("PORT", "8001"))
    _workers = int(os.environ.get("SQLAGENT_WORKERS", "1" if _reload else "4"))

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=_port,
        reload=_reload,
        workers=1 if _reload else _workers,  # reload requires single worker
        log_level="info",
    )



