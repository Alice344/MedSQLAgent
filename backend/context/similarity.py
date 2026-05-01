"""Shared text normalization and similarity helpers for NL-to-SQL memory."""

from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher

TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")
TOKEN_ALIASES = {
    "admission": "admit",
    "admissions": "admit",
    "admitted": "admit",
    "inpatient": "admit",
    "hospitalization": "admit",
    "hospitalizations": "admit",
    "hospitalized": "admit",
    "patients": "patient",
    "queries": "query",
}


def canonicalize_token(token: str) -> str:
    value = (token or "").lower()
    if value in TOKEN_ALIASES:
        return TOKEN_ALIASES[value]
    for suffix in (
        "ations",
        "ation",
        "ments",
        "ment",
        "ingly",
        "edly",
        "ingly",
        "ing",
        "ers",
        "ies",
        "ied",
        "ions",
        "ion",
        "ed",
        "es",
        "s",
    ):
        if len(value) > len(suffix) + 3 and value.endswith(suffix):
            if suffix in {"ies", "ied"}:
                value = value[: -len(suffix)] + "y"
            else:
                value = value[: -len(suffix)]
            break
    return TOKEN_ALIASES.get(value, value)


def tokenize_text(text: str) -> Counter[str]:
    return Counter(canonicalize_token(t) for t in TOKEN_RE.findall(text or ""))


def normalize_text(text: str) -> str:
    return " ".join(canonicalize_token(t) for t in TOKEN_RE.findall(text or ""))


def score_query_similarity(left: str, right: str) -> float:
    left_tokens = tokenize_text(left)
    right_tokens = tokenize_text(right)
    overlap = sum((left_tokens & right_tokens).values())
    total = sum((left_tokens | right_tokens).values()) or 1
    jaccard = overlap / total
    sequence = SequenceMatcher(None, left.lower(), right.lower()).ratio()
    left_norm = normalize_text(left)
    right_norm = normalize_text(right)
    if left_norm and left_norm == right_norm:
        return 1.0

    containment_boost = 0.0
    if left_norm and right_norm and (left_norm in right_norm or right_norm in left_norm):
        containment_boost = 0.12

    return min(1.0, (0.65 * jaccard) + (0.25 * sequence) + containment_boost)
