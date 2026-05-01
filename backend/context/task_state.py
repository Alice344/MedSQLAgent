"""Pending/completed task snapshot persistence mixin."""

from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional


class TaskStateMixin:
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
