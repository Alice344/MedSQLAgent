"""
Context-management package.

- ContextWindowManager – token-aware sliding window with auto-summarisation
- ConversationStore    – SQLite-backed persistent conversation + query history
"""

from .manager import ContextWindowManager
from .store import ConversationStore

__all__ = ["ContextWindowManager", "ConversationStore"]
