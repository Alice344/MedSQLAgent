"""Centralized rules for auto-maintained table markdown docs."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TABLE_DOCS_DIR = REPO_ROOT / "docs" / "caboodle"

MAX_RETRIEVED_CHUNKS = 5
CHUNK_CANDIDATE_MULTIPLIER = 4
MAX_CHUNKS_PER_TABLE = 1
MAX_HISTORY_EXAMPLES = 3
MAX_QUERY_EXAMPLES_PER_TABLE = 8
QUERY_RELEVANT_COLUMN_LIMIT = 12

EXAMPLE_QUERIES_HEADER = "## Example Queries"
SECTION_SCORE_WEIGHTS = {
    "used in": 1.4,
    "query notes": 1.3,
    "example queries": 1.25,
    "common joins": 1.1,
    "overview": 1.0,
    "query-relevant columns": 0.65,
    "document": 0.9,
}


def normalize_query_text(text: str) -> str:
    """Normalize NL text for de-duplication."""
    return re.sub(r"\s+", " ", text.strip().lower())
