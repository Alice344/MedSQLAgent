"""Retrieve relevant schema using markdown table docs plus controlled FK expansion."""

import math
import logging
import re
from collections import Counter, defaultdict
from typing import Any, Dict, List, Set

from table_docs.chunk_retriever import retrieve_relevant_doc_chunks

logger = logging.getLogger(__name__)
TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")
MAX_NEIGHBOR_TABLES = 8
HUB_DEGREE_THRESHOLD = 50


def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]


def _expand_tables_by_fk(
    query: str,
    selected_names: Set[str],
    all_tables: List[Dict[str, Any]],
    foreign_keys: List[Dict[str, Any]],
    depth: int,
) -> Set[str]:
    if depth <= 0 or not selected_names:
        return selected_names

    table_by_name = {table["full_name"]: table for table in all_tables}
    degree = Counter()
    for fk in foreign_keys:
        degree[fk["from_table"]] += 1
        degree[fk["to_table"]] += 1

    query_tokens = Counter(_tokenize(query))
    expanded = set(selected_names)
    frontier = set(selected_names)

    for _ in range(depth):
        candidate_links = defaultdict(int)
        for fk in foreign_keys:
            source_table = table_by_name.get(fk["from_table"])
            if (
                fk["from_table"] in frontier
                and source_table
                and str(source_table["name"]).endswith("Fact")
                and degree[fk["from_table"]] <= HUB_DEGREE_THRESHOLD
            ):
                candidate_links[fk["to_table"]] += 1

        ranked_neighbors = []
        for candidate, link_count in candidate_links.items():
            if candidate in expanded or candidate not in table_by_name:
                continue
            table = table_by_name[candidate]
            text_tokens = Counter(_tokenize(f"{table['name']} {table.get('description') or ''}"))
            overlap = sum((query_tokens & text_tokens).values())
            rarity_bonus = 1.0 / max(1.0, math.log2(degree[candidate] + 1.0))
            score = (3.0 * overlap) + (1.5 * link_count) + rarity_bonus
            ranked_neighbors.append((score, candidate))

        ranked_neighbors.sort(reverse=True)
        frontier = {candidate for _, candidate in ranked_neighbors[:MAX_NEIGHBOR_TABLES]} - expanded
        if not frontier:
            break
        expanded.update(frontier)
    return expanded


def retrieve_relevant_schema(
    schema: Dict[str, Any],
    query: str,
    top_k: int = 5,
    fk_neighbor_depth: int = 0,
) -> Dict[str, Any]:
    """
    Retrieval flow:
      1. Rank markdown table-doc chunks for the NL query.
      2. Map the top chunks back to schema tables.
      3. Expand by FK neighbors up to fk_neighbor_depth.
      4. Return the full schema for that expanded table set.
    """
    all_tables = schema.get("tables", [])
    all_fks = schema.get("foreign_keys", [])
    table_by_name: Dict[str, Dict[str, Any]] = {t["full_name"]: t for t in all_tables}

    chunks = retrieve_relevant_doc_chunks(query, top_k=top_k)
    logger.info("Retrieved %d relevant markdown chunks", len(chunks))

    selected_table_names: Set[str] = set()
    for chunk in chunks:
        table_short_name = chunk["table_name"]
        for table in all_tables:
            if table["name"] == table_short_name or table["full_name"].endswith(f".{table_short_name}"):
                selected_table_names.add(table["full_name"])
                break

    if not selected_table_names:
        logger.warning("No table docs matched query; falling back to first %d schema tables", top_k)
        selected_table_names = {t["full_name"] for t in all_tables[:top_k]}

    expanded_table_names = _expand_tables_by_fk(
        query,
        selected_table_names,
        all_tables,
        all_fks,
        fk_neighbor_depth,
    )
    selected = {name: table_by_name[name] for name in expanded_table_names if name in table_by_name}
    selected_set = set(selected)
    relevant_fks = [
        fk for fk in all_fks
        if fk["from_table"] in selected_set and fk["to_table"] in selected_set
    ]

    return {
        "tables": list(selected.values()),
        "foreign_keys": relevant_fks,
        "selected_tables": sorted(selected_table_names),
        "expanded_tables": sorted(selected_set),
        "selected_chunks": chunks,
    }
