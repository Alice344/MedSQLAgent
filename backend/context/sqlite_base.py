"""SQLite connection helpers shared by context store mixins."""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "conversations.db"


class SQLiteStoreBase:
    """Base class providing SQLite connection and row parsing helpers."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    @staticmethod
    def _parse_row_with_metadata(row: sqlite3.Row) -> Dict[str, Any]:
        item = dict(row)
        item["metadata"] = json.loads(item.get("metadata") or "{}")
        return item
