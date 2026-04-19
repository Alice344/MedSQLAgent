"""
Two-stage LLM schema retriever.

Stage 1: Send a compact table catalog (name + short description) to the LLM
         and ask it to pick the most relevant tables for the user's query.
Stage 2: Return the full schema for only those tables, keeping the SQL-generation
         prompt well within token limits.
"""
import json
import os
import re
import logging
from typing import Any, Dict, List

from llm.client import get_llm_client, get_model_name

logger = logging.getLogger(__name__)

# gpt-4o-mini supports 128K tokens; keep a buffer for system/user prompt + response
MAX_CATALOG_TOKENS = 100_000
CHARS_PER_TOKEN = 4  # conservative estimate


def _build_catalog(schema: Dict[str, Any], max_desc_len: int = 150) -> str:
    """Build a compact catalog: one line per table with name + truncated description.
    Truncates catalog if it would exceed the model's token limit."""
    lines = []
    total_chars = 0
    char_budget = MAX_CATALOG_TOKENS * CHARS_PER_TOKEN

    for tbl in schema.get("tables", []):
        name = tbl["full_name"]
        desc = (tbl.get("description") or "").replace("\n", " ").strip()
        if len(desc) > max_desc_len:
            desc = desc[:max_desc_len] + "..."
        line = f"{name} -- {desc}" if desc else name

        if total_chars + len(line) + 1 > char_budget:
            logger.warning(
                "Catalog truncated at %d tables (~%dK tokens) to stay within model limit",
                len(lines), total_chars // CHARS_PER_TOKEN // 1000,
            )
            break

        lines.append(line)
        total_chars += len(line) + 1  # +1 for newline

    return "\n".join(lines)


def _ask_llm_for_tables(catalog: str, query: str, top_k: int) -> List[str]:
    """Ask the LLM to pick the top_k most relevant table names from the catalog."""
    client = get_llm_client()
    model = get_model_name()

    system_prompt = f"""You are a database expert helping select relevant tables for a SQL query.
You will be given a list of database tables with short descriptions, and a user question.
Pick the {top_k} tables most likely needed to answer the question.

Return ONLY a JSON array of the exact full table names (e.g. ["dbo.PatientDim", "dbo.EncounterFact"]).
No explanation, no markdown fences, just the JSON array."""

    user_prompt = f"""Table catalog:
{catalog}

User question: {query}

Return the {top_k} most relevant table names as a JSON array:"""

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.0,
        max_tokens=2000,
    )

    raw = (response.choices[0].message.content or "").strip()

    # Strip DeepSeek-R1 reasoning blocks
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        selected = json.loads(raw)
        if isinstance(selected, list):
            return [str(t) for t in selected]
    except json.JSONDecodeError:
        logger.warning("LLM returned non-JSON table selection: %s", raw)

    # Fallback: try to extract table names from the raw string
    return [t.strip().strip('"').strip("'") for t in raw.split(",") if "." in t]


def retrieve_relevant_schema(
    schema: Dict[str, Any],
    query: str,
    top_k: int = 5,
    fk_neighbor_depth: int = 0,
) -> Dict[str, Any]:
    """
    Two-stage retrieval:
      Stage 1 — LLM picks top_k tables from a compact catalog.
      Stage 2 — Return those tables' full schema + FK edges between them.
    """
    all_tables = schema.get("tables", [])
    all_fks = schema.get("foreign_keys", [])
    table_by_name: Dict[str, Dict[str, Any]] = {t["full_name"]: t for t in all_tables}

    # Stage 1: build catalog and ask LLM
    catalog = _build_catalog(schema)
    logger.info(
        "Table catalog: %d tables, ~%d chars (~%dK tokens)",
        len(all_tables), len(catalog), len(catalog) // CHARS_PER_TOKEN // 1000,
    )

    try:
        selected_names = _ask_llm_for_tables(catalog, query, top_k)
        logger.info("LLM selected tables: %s", selected_names)
    except Exception as e:
        logger.error("LLM table selection failed, falling back to first %d tables: %s", top_k, e)
        selected_names = [t["full_name"] for t in all_tables[:top_k]]

    # Resolve names to table dicts
    selected: Dict[str, Dict[str, Any]] = {}
    for name in selected_names:
        if name in table_by_name:
            selected[name] = table_by_name[name]
        else:
            logger.warning("LLM picked unknown table '%s', skipping", name)

    if not selected:
        logger.warning("No valid tables selected, falling back to first %d", top_k)
        for tbl in all_tables[:top_k]:
            selected[tbl["full_name"]] = tbl

    # Filter FK edges to only those between selected tables
    selected_set = set(selected.keys())
    relevant_fks = [
        fk for fk in all_fks
        if fk["from_table"] in selected_set and fk["to_table"] in selected_set
    ]

    return {"tables": list(selected.values()), "foreign_keys": relevant_fks}
