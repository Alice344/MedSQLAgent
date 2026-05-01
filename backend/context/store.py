"""
Persistent conversation & query-history store backed by SQLite.

Tables
------
conversations  – one row per connection_id session
messages       – individual turns within a conversation
query_history  – every SQL query executed (with metadata)
task_state     – persisted pending/completed agent task snapshots

The DB file lives at ``backend/data/conversations.db`` by default.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "conversations.db"
TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


class ConversationStore:
    """Thread-safe SQLite store for conversations and query history."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ── Setup ────────────────────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id            TEXT PRIMARY KEY,
                    connection_id TEXT NOT NULL,
                    created_at    REAL NOT NULL,
                    updated_at    REAL NOT NULL,
                    summary       TEXT DEFAULT '',
                    metadata      TEXT DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_conv_conn
                    ON conversations(connection_id);

                CREATE TABLE IF NOT EXISTS messages (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role            TEXT NOT NULL,
                    content         TEXT NOT NULL,
                    agent           TEXT,
                    timestamp       REAL NOT NULL,
                    metadata        TEXT DEFAULT '{}',
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                );

                CREATE INDEX IF NOT EXISTS idx_msg_conv
                    ON messages(conversation_id);

                CREATE TABLE IF NOT EXISTS query_history (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    connection_id   TEXT NOT NULL,
                    conversation_id TEXT,
                    task_id         TEXT,
                    user_query      TEXT NOT NULL,
                    generated_sql   TEXT,
                    row_count       INTEGER,
                    status          TEXT NOT NULL DEFAULT 'completed',
                    error           TEXT,
                    created_at      REAL NOT NULL,
                    metadata        TEXT DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_qh_conn
                    ON query_history(connection_id);

                CREATE TABLE IF NOT EXISTS task_state (
                    task_id         TEXT PRIMARY KEY,
                    connection_id   TEXT NOT NULL,
                    conversation_id TEXT,
                    status          TEXT NOT NULL,
                    payload         TEXT NOT NULL,
                    updated_at      REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_task_state_conn
                    ON task_state(connection_id);
                """
            )
        logger.info("ConversationStore initialised at %s", self.db_path)

    # ── Conversations ────────────────────────────────────────────────────

    def get_or_create_conversation(self, connection_id: str) -> str:
        """Return the active conversation id for a connection, creating if needed."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id FROM conversations WHERE connection_id = ? ORDER BY updated_at DESC LIMIT 1",
                (connection_id,),
            ).fetchone()
            if row:
                return row["id"]

            import uuid

            conv_id = uuid.uuid4().hex[:16]
            now = time.time()
            conn.execute(
                "INSERT INTO conversations (id, connection_id, created_at, updated_at) VALUES (?,?,?,?)",
                (conv_id, connection_id, now, now),
            )
            return conv_id

    def new_conversation(self, connection_id: str) -> str:
        """Start a fresh conversation for a connection (e.g. user clicks 'New Chat')."""
        import uuid

        conv_id = uuid.uuid4().hex[:16]
        now = time.time()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO conversations (id, connection_id, created_at, updated_at) VALUES (?,?,?,?)",
                (conv_id, connection_id, now, now),
            )
        return conv_id

    def update_conversation_summary(self, conversation_id: str, summary: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE conversations SET summary = ?, updated_at = ? WHERE id = ?",
                (summary, time.time(), conversation_id),
            )

    def get_conversation_summary(self, conversation_id: str) -> str:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT summary FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
            return row["summary"] if row else ""

    # ── Messages ─────────────────────────────────────────────────────────

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        agent: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        now = time.time()
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO messages (conversation_id, role, content, agent, timestamp, metadata) "
                "VALUES (?,?,?,?,?,?)",
                (
                    conversation_id,
                    role,
                    content,
                    agent,
                    now,
                    json.dumps(metadata or {}),
                ),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conversation_id),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def get_messages(
        self,
        conversation_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT role, content, agent, timestamp, metadata FROM messages "
                "WHERE conversation_id = ? ORDER BY timestamp ASC LIMIT ? OFFSET ?",
                (conversation_id, limit, offset),
            ).fetchall()
            return [
                {
                    "role": r["role"],
                    "content": r["content"],
                    "agent": r["agent"],
                    "timestamp": r["timestamp"],
                    "metadata": json.loads(r["metadata"]),
                }
                for r in rows
            ]

    def get_recent_messages_for_connection(
        self, connection_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get the most recent messages across all conversations for a connection."""
        conv_id = self.get_or_create_conversation(connection_id)
        return self.get_messages(conv_id, limit=limit)

    # ── Query History ────────────────────────────────────────────────────

    def add_query_history(
        self,
        connection_id: str,
        user_query: str,
        generated_sql: Optional[str] = None,
        row_count: Optional[int] = None,
        status: str = "completed",
        error: Optional[str] = None,
        conversation_id: Optional[str] = None,
        task_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO query_history "
                "(connection_id, conversation_id, task_id, user_query, generated_sql, "
                "row_count, status, error, created_at, metadata) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    connection_id,
                    conversation_id,
                    task_id,
                    user_query,
                    generated_sql,
                    row_count,
                    status,
                    error,
                    time.time(),
                    json.dumps(metadata or {}),
                ),
            )
            logger.info(
                "Stored query_history row id=%s task_id=%s connection_id=%s status=%s row_count=%s query=%r",
                cur.lastrowid,
                task_id,
                connection_id,
                status,
                row_count,
                user_query[:160],
            )
            return cur.lastrowid  # type: ignore[return-value]

    def get_query_history(
        self, connection_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT task_id, user_query, generated_sql, row_count, status, error, created_at "
                "FROM query_history WHERE connection_id = ? ORDER BY created_at DESC LIMIT ?",
                (connection_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def find_similar_query_examples(
        self,
        user_query: str,
        limit: int = 3,
        candidate_limit: int = 200,
        connection_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return the most similar historical NL/SQL pairs."""

        def tokenize(text: str) -> Counter[str]:
            return Counter(t.lower() for t in TOKEN_RE.findall(text or ""))

        def normalize(text: str) -> str:
            return " ".join(TOKEN_RE.findall((text or "").lower()))

        def similarity_score(left: str, right: str) -> float:
            left_tokens = tokenize(left)
            right_tokens = tokenize(right)
            overlap = sum((left_tokens & right_tokens).values())
            total = sum((left_tokens | right_tokens).values()) or 1
            jaccard = overlap / total
            sequence = SequenceMatcher(None, left.lower(), right.lower()).ratio()
            left_norm = normalize(left)
            right_norm = normalize(right)
            if left_norm and left_norm == right_norm:
                return 1.0

            containment_boost = 0.0
            if left_norm and right_norm and (left_norm in right_norm or right_norm in left_norm):
                containment_boost = 0.12

            return min(1.0, (0.65 * jaccard) + (0.25 * sequence) + containment_boost)

        with self._conn() as conn:
            if connection_id:
                rows = conn.execute(
                    """
                    SELECT connection_id, user_query, generated_sql, created_at
                    FROM query_history
                    WHERE generated_sql IS NOT NULL
                      AND TRIM(generated_sql) <> ''
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (candidate_limit,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT connection_id, user_query, generated_sql, created_at
                    FROM query_history
                    WHERE generated_sql IS NOT NULL
                      AND TRIM(generated_sql) <> ''
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (candidate_limit,),
                ).fetchall()

        scored: List[Dict[str, Any]] = []
        for row in rows:
            score = similarity_score(user_query, row["user_query"])
            if connection_id and row["connection_id"] == connection_id:
                score += 0.05
            scored.append(
                {
                    "connection_id": row["connection_id"],
                    "user_query": row["user_query"],
                    "generated_sql": row["generated_sql"],
                    "created_at": row["created_at"],
                    "score": score,
                    "match_strength": (
                        "high" if score >= 0.72 else "medium" if score >= 0.45 else "low"
                    ),
                }
            )

        ranked = sorted(
            scored,
            key=lambda item: (item["score"], item["created_at"]),
            reverse=True,
        )
        non_zero = [item for item in ranked if item["score"] > 0]
        selected = (non_zero or ranked)[:limit]
        logger.info(
            "Retrieved %s similar examples for query=%r top_scores=%s",
            len(selected),
            user_query[:160],
            [
                {
                    "score": round(item["score"], 3),
                    "strength": item["match_strength"],
                    "query": item["user_query"][:100],
                }
                for item in selected
            ],
        )
        return selected

    # ── Task State ───────────────────────────────────────────────────────

    def save_task_state(
        self,
        task_id: str,
        connection_id: str,
        status: str,
        payload: Dict[str, Any],
        conversation_id: Optional[str] = None,
    ) -> None:
        now = time.time()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO task_state (task_id, connection_id, conversation_id, status, payload, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    connection_id=excluded.connection_id,
                    conversation_id=excluded.conversation_id,
                    status=excluded.status,
                    payload=excluded.payload,
                    updated_at=excluded.updated_at
                """,
                (
                    task_id,
                    connection_id,
                    conversation_id,
                    status,
                    json.dumps(payload),
                    now,
                ),
            )

    def get_task_state(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT task_id, connection_id, conversation_id, status, payload, updated_at
                FROM task_state
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
            if not row:
                return None
            return {
                "task_id": row["task_id"],
                "connection_id": row["connection_id"],
                "conversation_id": row["conversation_id"],
                "status": row["status"],
                "payload": json.loads(row["payload"]),
                "updated_at": row["updated_at"],
            }

    def delete_task_state(self, task_id: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM task_state WHERE task_id = ?", (task_id,))

    def clear_task_state_for_connection(self, connection_id: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM task_state WHERE connection_id = ?", (connection_id,))

    # ── Cleanup ──────────────────────────────────────────────────────────

    def clear_conversation(self, connection_id: str) -> None:
        """Delete all conversations and messages for a connection."""
        with self._conn() as conn:
            conv_ids = [
                r["id"]
                for r in conn.execute(
                    "SELECT id FROM conversations WHERE connection_id = ?",
                    (connection_id,),
                ).fetchall()
            ]
            if conv_ids:
                placeholders = ",".join("?" * len(conv_ids))
                conn.execute(
                    f"DELETE FROM messages WHERE conversation_id IN ({placeholders})",
                    conv_ids,
                )
                conn.execute(
                    f"DELETE FROM conversations WHERE id IN ({placeholders})",
                    conv_ids,
                )
            conn.execute("DELETE FROM task_state WHERE connection_id = ?", (connection_id,))
        logger.info("Cleared conversations for connection %s", connection_id)
