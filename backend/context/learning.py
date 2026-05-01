"""Learning, attempt tracking, and skill persistence mixins."""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from .similarity import score_query_similarity


class LearningStoreMixin:
    def add_query_attempt(
        self,
        connection_id: str,
        task_id: str,
        user_query: str,
        generated_sql: Optional[str],
        status: str,
        conversation_id: Optional[str] = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        now = time.time()
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO query_attempts
                (connection_id, conversation_id, task_id, user_query, generated_sql, status, error, created_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    connection_id,
                    conversation_id,
                    task_id,
                    user_query,
                    generated_sql,
                    status,
                    error,
                    now,
                    now,
                    json.dumps(metadata or {}),
                ),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def update_query_attempt(
        self,
        task_id: str,
        status: str,
        generated_sql: Optional[str] = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT metadata FROM query_attempts WHERE task_id = ? ORDER BY id DESC LIMIT 1",
                (task_id,),
            ).fetchone()
            existing_meta = json.loads(row["metadata"]) if row and row["metadata"] else {}
            merged_meta = {**existing_meta, **(metadata or {})}
            conn.execute(
                """
                UPDATE query_attempts
                SET status = ?,
                    generated_sql = COALESCE(?, generated_sql),
                    error = ?,
                    updated_at = ?,
                    metadata = ?
                WHERE id = (
                    SELECT id FROM query_attempts WHERE task_id = ? ORDER BY id DESC LIMIT 1
                )
                """,
                (
                    status,
                    generated_sql,
                    error,
                    time.time(),
                    json.dumps(merged_meta),
                    task_id,
                ),
            )

    def add_query_correction(
        self,
        connection_id: str,
        user_query: str,
        original_sql: str,
        corrected_sql: str,
        correction_kind: str = "manual_edit",
        conversation_id: Optional[str] = None,
        task_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO query_corrections
                (connection_id, conversation_id, task_id, user_query, original_sql, corrected_sql, correction_kind, created_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    connection_id,
                    conversation_id,
                    task_id,
                    user_query,
                    original_sql,
                    corrected_sql,
                    correction_kind,
                    time.time(),
                    json.dumps(metadata or {}),
                ),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def upsert_skill_candidate(
        self,
        connection_id: str,
        candidate_key: str,
        title: str,
        summary: str,
        trigger_query: str,
        representative_sql: Optional[str],
        confidence: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        now = time.time()
        payload = json.dumps(metadata or {})
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT id, status FROM skill_candidates WHERE candidate_key = ?",
                (candidate_key,),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE skill_candidates
                    SET title = ?, summary = ?, trigger_query = ?, representative_sql = ?,
                        confidence = ?, updated_at = ?, metadata = ?
                    WHERE id = ?
                    """,
                    (
                        title,
                        summary,
                        trigger_query,
                        representative_sql,
                        confidence,
                        now,
                        payload,
                        existing["id"],
                    ),
                )
                return int(existing["id"])

            cur = conn.execute(
                """
                INSERT INTO skill_candidates
                (connection_id, candidate_key, title, summary, trigger_query, representative_sql, confidence, status, created_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
                """,
                (
                    connection_id,
                    candidate_key,
                    title,
                    summary,
                    trigger_query,
                    representative_sql,
                    confidence,
                    now,
                    now,
                    payload,
                ),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def list_skill_candidates(
        self,
        connection_id: str,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            if status:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM skill_candidates
                    WHERE connection_id = ? AND status = ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (connection_id, status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM skill_candidates
                    WHERE connection_id = ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (connection_id, limit),
                ).fetchall()
            return [self._parse_row_with_metadata(row) for row in rows]

    def get_skill_candidate(self, candidate_id: int) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM skill_candidates WHERE id = ?",
                (candidate_id,),
            ).fetchone()
            return self._parse_row_with_metadata(row) if row else None

    def publish_skill_candidate(
        self,
        candidate_id: int,
        review_notes: str = "",
        edited_title: Optional[str] = None,
        edited_instructions: Optional[str] = None,
    ) -> Optional[int]:
        candidate = self.get_skill_candidate(candidate_id)
        if not candidate:
            return None

        metadata = candidate.get("metadata", {})
        instructions = edited_instructions or metadata.get("instructions") or candidate["summary"]
        title = edited_title or candidate["title"]
        now = time.time()
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO published_skills
                (connection_id, skill_candidate_id, title, summary, instructions, status, created_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)
                """,
                (
                    candidate["connection_id"],
                    candidate_id,
                    title,
                    candidate["summary"],
                    instructions,
                    now,
                    now,
                    json.dumps(metadata),
                ),
            )
            merged_meta = {**metadata, "review_notes": review_notes}
            conn.execute(
                """
                UPDATE skill_candidates
                SET status = 'approved', updated_at = ?, metadata = ?
                WHERE id = ?
                """,
                (now, json.dumps(merged_meta), candidate_id),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def reject_skill_candidate(self, candidate_id: int, review_notes: str = "") -> None:
        candidate = self.get_skill_candidate(candidate_id)
        if not candidate:
            return
        metadata = {**candidate.get("metadata", {}), "review_notes": review_notes}
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE skill_candidates
                SET status = 'rejected', updated_at = ?, metadata = ?
                WHERE id = ?
                """,
                (time.time(), json.dumps(metadata), candidate_id),
            )

    def list_published_skills(
        self,
        connection_id: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM published_skills
                WHERE connection_id = ? AND status = 'active'
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (connection_id, limit),
            ).fetchall()
            return [self._parse_row_with_metadata(row) for row in rows]

    def find_matching_published_skills(
        self,
        connection_id: str,
        user_query: str,
        selected_tables: Optional[List[str]] = None,
        limit: int = 2,
    ) -> List[Dict[str, Any]]:
        candidates = self.list_published_skills(connection_id, limit=50)
        selected_set = {item.lower() for item in (selected_tables or [])}
        scored: List[Dict[str, Any]] = []
        for skill in candidates:
            metadata = skill.get("metadata", {})
            score = score_query_similarity(user_query, skill.get("trigger_query", ""))
            query_examples = metadata.get("example_queries", [])
            if query_examples:
                score = max(score, max(score_query_similarity(user_query, q) for q in query_examples))

            skill_tables = {str(t).lower() for t in metadata.get("selected_tables", [])}
            if selected_set and skill_tables:
                overlap = len(selected_set & skill_tables) / max(len(selected_set | skill_tables), 1)
                score += 0.2 * overlap

            if score < 0.35:
                continue
            scored.append({**skill, "match_score": min(score, 1.0)})

        ranked = sorted(scored, key=lambda item: item["match_score"], reverse=True)
        return ranked[:limit]

    def add_skill_usage(
        self,
        connection_id: str,
        published_skill_id: int,
        user_query: str,
        outcome: str,
        task_id: Optional[str] = None,
        match_score: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO skill_usage_history
                (connection_id, task_id, published_skill_id, user_query, match_score, outcome, created_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    connection_id,
                    task_id,
                    published_skill_id,
                    user_query,
                    match_score,
                    outcome,
                    time.time(),
                    json.dumps(metadata or {}),
                ),
            )
            return cur.lastrowid  # type: ignore[return-value]
