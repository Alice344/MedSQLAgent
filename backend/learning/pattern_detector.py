"""Detect repeated successful patterns and promote them to skill candidates."""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any, Dict, List, Optional

from context.similarity import normalize_text, score_query_similarity
from skills.policy import (
    MAX_EXAMPLE_QUERIES,
    MAX_EXAMPLE_SQLS,
    MIN_AVG_SIMILARITY,
    MIN_PATTERN_OCCURRENCES,
    MIN_TOP_SIMILARITY,
)

logger = logging.getLogger(__name__)


def maybe_create_skill_candidate(
    conversation_store: Any,
    *,
    connection_id: str,
    task_id: str,
    user_query: str,
    generated_sql: str,
    selected_tables: List[str],
) -> Optional[int]:
    successful = conversation_store.get_recent_successful_queries(connection_id, limit=200)
    related = []
    for item in successful:
        if item.get("task_id") == task_id:
            continue
        metadata = item.get("metadata", {})
        score = score_query_similarity(user_query, item.get("user_query", ""))
        table_overlap = _score_table_overlap(selected_tables, metadata.get("selected_tables", []))
        combined = min(1.0, (0.78 * score) + (0.22 * table_overlap))
        if combined >= 0.5:
            related.append(
                {
                    **item,
                    "metadata": metadata,
                    "similarity": combined,
                    "table_overlap": table_overlap,
                }
            )

    related = sorted(related, key=lambda item: item["similarity"], reverse=True)
    if len(related) + 1 < MIN_PATTERN_OCCURRENCES:
        logger.info(
            "No skill candidate for task=%s; only %s similar successful queries found",
            task_id,
            len(related),
        )
        return None

    top_related = related[: MAX_EXAMPLE_QUERIES - 1]
    avg_similarity = sum(item["similarity"] for item in top_related) / max(len(top_related), 1)
    top_similarity = top_related[0]["similarity"] if top_related else 0.0
    if avg_similarity < MIN_AVG_SIMILARITY or top_similarity < MIN_TOP_SIMILARITY:
        logger.info(
            "No skill candidate for task=%s; avg_similarity=%.3f top_similarity=%.3f",
            task_id,
            avg_similarity,
            top_similarity,
        )
        return None

    example_queries = [user_query] + [item["user_query"] for item in top_related]
    example_sqls = [generated_sql] + [item.get("generated_sql", "") for item in top_related]
    normalized_queries = [normalize_text(item) for item in example_queries]
    representative_terms = _top_terms(normalized_queries)
    title = _build_title(user_query, representative_terms)
    candidate_key = _candidate_key(connection_id, selected_tables, representative_terms)
    summary = (
        f"Observed {len(top_related) + 1} highly similar successful queries that repeatedly use "
        f"{', '.join(selected_tables[:4]) or 'the same schema pattern'}."
    )
    instructions = _build_instructions(selected_tables, example_queries, generated_sql)

    candidate_id = conversation_store.upsert_skill_candidate(
        connection_id=connection_id,
        candidate_key=candidate_key,
        title=title,
        summary=summary,
        trigger_query=user_query,
        representative_sql=generated_sql,
        confidence=round((avg_similarity + top_similarity) / 2, 4),
        metadata={
            "source_task_id": task_id,
            "selected_tables": selected_tables,
            "example_queries": example_queries[:MAX_EXAMPLE_QUERIES],
            "example_sqls": [sql for sql in example_sqls[:MAX_EXAMPLE_SQLS] if sql],
            "avg_similarity": round(avg_similarity, 4),
            "top_similarity": round(top_similarity, 4),
            "instructions": instructions,
            "representative_terms": representative_terms,
            "source_query_ids": [item["id"] for item in top_related],
        },
    )
    logger.info(
        "Created/updated skill candidate id=%s title=%r confidence=%.3f",
        candidate_id,
        title,
        (avg_similarity + top_similarity) / 2,
    )
    return candidate_id


def _score_table_overlap(current_tables: List[str], previous_tables: List[str]) -> float:
    current = {str(item).lower() for item in current_tables}
    previous = {str(item).lower() for item in previous_tables}
    if not current or not previous:
        return 0.0
    return len(current & previous) / max(len(current | previous), 1)


def _top_terms(queries: List[str]) -> List[str]:
    counts: Dict[str, int] = {}
    stop_words = {
        "find", "show", "list", "get", "for", "with", "the", "and", "from", "that",
        "patients", "patient", "records", "query", "sql",
    }
    for query in queries:
        for token in query.split():
            if len(token) < 3 or token in stop_words:
                continue
            counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [term for term, _ in ranked[:4]]


def _build_title(user_query: str, representative_terms: List[str]) -> str:
    if representative_terms:
        return " / ".join(term.replace("_", " ").title() for term in representative_terms) + " Skill"
    cleaned = re.sub(r"\s+", " ", user_query).strip()
    return cleaned[:48].title() + (" Skill" if len(cleaned) <= 48 else "...")


def _candidate_key(connection_id: str, selected_tables: List[str], representative_terms: List[str]) -> str:
    raw = "|".join(
        [
            connection_id,
            ",".join(sorted(selected_tables)),
            ",".join(representative_terms),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _build_instructions(selected_tables: List[str], example_queries: List[str], generated_sql: str) -> str:
    table_summary = ", ".join(selected_tables[:5]) or "the same schema pattern"
    trigger_summary = "; ".join(example_queries[:3])
    return (
        f"When the user asks a very similar cohort or analytics question, start from {table_summary}. "
        f"Prefer the joins and filtering shape from the representative SQL. "
        f"Typical triggers look like: {trigger_summary}. "
        f"Representative SQL starts with: {generated_sql[:240]}"
    )
