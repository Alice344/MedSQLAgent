"""Retrieve relevant table-doc markdown chunks for a user question."""

from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List

from .merge_rules import MAX_RETRIEVED_CHUNKS, TABLE_DOCS_DIR

TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")
HEADER_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]


def _split_markdown_into_chunks(path: Path) -> List[Dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    table_name = path.stem
    lines = text.splitlines()

    chunks: List[Dict[str, str]] = []
    current_title = "Document"
    current_lines: List[str] = []

    def flush() -> None:
        content = "\n".join(current_lines).strip()
        if not content:
            return
        chunks.append(
            {
                "table_name": table_name,
                "chunk_title": current_title,
                "content": content,
            }
        )

    for line in lines:
        match = HEADER_RE.match(line)
        if match and len(match.group(1)) <= 3:
            flush()
            current_title = match.group(2).strip()
            current_lines = [line]
            continue
        current_lines.append(line)

    flush()
    return chunks


def load_doc_chunks(docs_dir: Path = TABLE_DOCS_DIR) -> List[Dict[str, str]]:
    chunks: List[Dict[str, str]] = []
    if not docs_dir.exists():
        return chunks

    for path in sorted(docs_dir.glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        chunks.extend(_split_markdown_into_chunks(path))
    return chunks


def retrieve_relevant_doc_chunks(
    query: str,
    top_k: int = MAX_RETRIEVED_CHUNKS,
    docs_dir: Path = TABLE_DOCS_DIR,
) -> List[Dict[str, str]]:
    chunks = load_doc_chunks(docs_dir)
    if not chunks:
        return []

    query_tokens = _tokenize(query)
    if not query_tokens:
        return chunks[:top_k]

    query_counts = Counter(query_tokens)
    doc_freq = Counter()
    chunk_token_counts: List[Counter[str]] = []

    for chunk in chunks:
        tokens = _tokenize(f"{chunk['chunk_title']} {chunk['content']}")
        counts = Counter(tokens)
        chunk_token_counts.append(counts)
        for token in counts:
            doc_freq[token] += 1

    total_chunks = len(chunks)
    scored: List[Dict[str, str]] = []

    for chunk, token_counts in zip(chunks, chunk_token_counts):
        score = 0.0
        for token, q_tf in query_counts.items():
            doc_tf = token_counts.get(token, 0)
            if not doc_tf:
                continue
            idf = math.log((1 + total_chunks) / (1 + doc_freq[token])) + 1.0
            score += q_tf * doc_tf * idf

        if score > 0:
            score += 0.1 * len(set(query_tokens) & set(token_counts))

        scored.append({**chunk, "score": f"{score:.6f}"})

    ranked = sorted(scored, key=lambda c: float(c["score"]), reverse=True)
    non_zero = [chunk for chunk in ranked if float(chunk["score"]) > 0]
    if non_zero:
        return non_zero[:top_k]
    return ranked[:top_k]
