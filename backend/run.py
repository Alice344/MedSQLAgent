"""
Simple script to run the FastAPI server.

Set SQLAGENT_RELOAD=0 to disable auto-reload (stops losing in-memory DB sessions
when you save Python files). Default is reload on for development.
"""
import os

import uvicorn

if __name__ == "__main__":
    _reload = os.environ.get("SQLAGENT_RELOAD", "1").lower() not in (
        "0",
        "false",
        "no",
    )
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=_reload,
        log_level="info",
    )



