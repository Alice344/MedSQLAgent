"""
SQLite-backed memory facade for conversations, query history, learning, and task state.

This module intentionally stays small and re-exports the public helpers that the
rest of the codebase already imports from `context.store`.
"""
from __future__ import annotations

import logging
from typing import Optional

from .conversations import ConversationHistoryMixin
from .db_schema import init_context_store_schema
from .learning import LearningStoreMixin
from .similarity import (
    canonicalize_token,
    normalize_text,
    score_query_similarity,
    tokenize_text,
)
from .sqlite_base import SQLiteStoreBase
from .task_state import TaskStateMixin

logger = logging.getLogger(__name__)


class ConversationStore(
    ConversationHistoryMixin,
    LearningStoreMixin,
    TaskStateMixin,
    SQLiteStoreBase,
):
    """Facade that composes the smaller SQLite store mixins."""

    def __init__(self, db_path: Optional[str] = None):
        super().__init__(db_path=db_path)
        with self._conn() as conn:
            init_context_store_schema(conn)
        logger.info("ConversationStore initialised at %s", self.db_path)


__all__ = [
    "ConversationStore",
    "canonicalize_token",
    "tokenize_text",
    "normalize_text",
    "score_query_similarity",
]
