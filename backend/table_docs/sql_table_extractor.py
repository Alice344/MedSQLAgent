"""Extract schema tables referenced by SQL."""

from __future__ import annotations

import re
from typing import Dict, Iterable, List

TABLE_PATTERN = re.compile(
    r"\b(?:FROM|JOIN|INTO|UPDATE|MERGE\s+INTO|DELETE\s+FROM)\s+"
    r"([A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*|[A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)


def extract_schema_tables(sql: str, schema_tables: Iterable[Dict[str, object]]) -> List[Dict[str, object]]:
    """Return schema table dicts referenced by SQL, excluding temp objects."""
    all_tables = list(schema_tables)
    by_full_name = {str(t["full_name"]).lower(): t for t in all_tables}
    by_short_name = {str(t["name"]).lower(): t for t in all_tables}

    seen = set()
    matched: List[Dict[str, object]] = []

    for raw_name in TABLE_PATTERN.findall(sql or ""):
        if raw_name.startswith("#"):
            continue

        key = raw_name.lower()
        table = by_full_name.get(key)
        if not table:
            short_name = key.split(".", 1)[-1]
            table = by_short_name.get(short_name)
        if not table:
            continue

        full_name = str(table["full_name"])
        if full_name in seen:
            continue
        seen.add(full_name)
        matched.append(table)

    return matched
