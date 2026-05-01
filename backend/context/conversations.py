"""Conversation, message, and query-history mixins for ConversationStore."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

from .similarity import score_query_similarity

logger = logging.getLogger(__name__)


class ConversationHistoryMixin:
    def get_or_create_conversation(self, connection_id: str) -> str:
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
        conv_id = self.get_or_create_conversation(connection_id)
        return self.get_messages(conv_id, limit=limit)

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
        with self._conn() as conn:
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
            score = score_query_similarity(user_query, row["user_query"])
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

    def get_recent_successful_queries(
        self, connection_id: str, limit: int = 200
    ) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, connection_id, conversation_id, task_id, user_query, generated_sql,
                       row_count, status, error, created_at, metadata
                FROM query_history
                WHERE connection_id = ?
                  AND status = 'completed'
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (connection_id, limit),
            ).fetchall()
            return [self._parse_row_with_metadata(row) for row in rows]

    def clear_conversation(self, connection_id: str) -> None:
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
