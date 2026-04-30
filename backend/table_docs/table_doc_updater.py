"""Create and update per-table markdown docs after successful queries."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .merge_rules import (
    EXAMPLE_QUERIES_HEADER,
    MAX_QUERY_EXAMPLES_PER_TABLE,
    QUERY_RELEVANT_COLUMN_LIMIT,
    TABLE_DOCS_DIR,
    normalize_query_text,
)
from .sql_table_extractor import extract_schema_tables


def _render_common_joins(table: Dict[str, Any], foreign_keys: Iterable[Dict[str, Any]]) -> List[str]:
    lines: List[str] = []
    full_name = table["full_name"]
    for fk in foreign_keys:
        if fk["from_table"] == full_name:
            target = fk["to_table"].split(".", 1)[-1]
            lines.append(
                f"- `{table['name']}.{fk['from_column']} = {target}.{fk['to_column']}`"
            )
        elif fk["to_table"] == full_name:
            source = fk["from_table"].split(".", 1)[-1]
            lines.append(
                f"- `{table['name']}.{fk['to_column']} = {source}.{fk['from_column']}`"
            )
    return lines[:8] or ["- None documented yet"]


def _render_query_relevant_columns(table: Dict[str, Any]) -> str:
    rows = [
        "| Column | Type | Nullable | Notes |",
        "| --- | --- | --- | --- |",
    ]
    for col in table.get("columns", [])[:QUERY_RELEVANT_COLUMN_LIMIT]:
        rows.append(
            f"| `{col['name']}` | `{col['data_type']}` | "
            f"{'Yes' if col['is_nullable'] else 'No'} | "
            f"{(col.get('description') or '').replace('|', '/')} |"
        )
    return "\n".join(rows)


def _render_new_doc(table: Dict[str, Any], foreign_keys: Iterable[Dict[str, Any]], nl_query: str) -> str:
    description = table.get("description") or "No description available."
    common_joins = "\n".join(_render_common_joins(table, foreign_keys))
    columns_md = _render_query_relevant_columns(table)

    return "\n".join(
        [
            f"# `caboodle.{table['name']}`",
            "",
            "## Overview",
            "",
            f"- Schema source name: `{table['full_name']}`",
            f"- Column count in `wholegraph.json`: `{len(table.get('columns', []))}`",
            f"- Description: {description}",
            "",
            "## Common Joins",
            "",
            common_joins,
            "",
            "## Query-Relevant Columns",
            "",
            columns_md,
            "",
            EXAMPLE_QUERIES_HEADER,
            "",
            f"- {nl_query.strip()}",
            "",
            "## Query Notes",
            "",
            "- Auto-maintained from executed NL-to-SQL pairs.",
            "",
        ]
    )


def _upsert_example_query(existing_text: str, nl_query: str) -> str:
    normalized_target = normalize_query_text(nl_query)
    lines = existing_text.splitlines()

    try:
        start_idx = lines.index(EXAMPLE_QUERIES_HEADER)
    except ValueError:
        suffix = "\n" if existing_text.endswith("\n") else "\n\n"
        return f"{existing_text.rstrip()}{suffix}{EXAMPLE_QUERIES_HEADER}\n\n- {nl_query.strip()}\n"

    end_idx = len(lines)
    for i in range(start_idx + 1, len(lines)):
        if re.match(r"^##\s+", lines[i]):
            end_idx = i
            break

    existing_examples: List[str] = []
    for line in lines[start_idx + 1 : end_idx]:
        stripped = line.strip()
        if stripped.startswith("- "):
            existing_examples.append(stripped[2:].strip())

    deduped = []
    seen = set()
    for example in [nl_query.strip(), *existing_examples]:
        normalized = normalize_query_text(example)
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(example)

    if normalized_target not in seen:
        deduped.insert(0, nl_query.strip())

    deduped = deduped[:MAX_QUERY_EXAMPLES_PER_TABLE]

    new_block = [EXAMPLE_QUERIES_HEADER, ""]
    new_block.extend(f"- {example}" for example in deduped)
    new_block.append("")

    rebuilt = lines[:start_idx] + new_block + lines[end_idx:]
    return "\n".join(rebuilt).rstrip() + "\n"


def update_table_docs_for_query(
    schema: Dict[str, Any],
    sql_query: str,
    natural_language_query: str,
    docs_dir: Path = TABLE_DOCS_DIR,
) -> List[Path]:
    docs_dir.mkdir(parents=True, exist_ok=True)

    touched: List[Path] = []
    matched_tables = extract_schema_tables(sql_query, schema.get("tables", []))
    for table in matched_tables:
        path = docs_dir / f"{table['name']}.md"
        if path.exists():
            updated = _upsert_example_query(path.read_text(encoding="utf-8"), natural_language_query)
            path.write_text(updated, encoding="utf-8")
        else:
            content = _render_new_doc(table, schema.get("foreign_keys", []), natural_language_query)
            path.write_text(content, encoding="utf-8")
        touched.append(path)

    return touched
