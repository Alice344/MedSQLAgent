"""
Context-window manager.

Keeps a rolling conversation history, counts tokens, and automatically
summarises older messages when the window budget is exceeded.

Token counting uses tiktoken (cl100k_base for GPT-4 family).
If tiktoken is unavailable, falls back to a rough char/4 estimate.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Token counting ───────────────────────────────────────────────────────────

try:
    import tiktoken

    _ENC = tiktoken.get_encoding("cl100k_base")

    def count_tokens(text: str) -> int:
        return len(_ENC.encode(text))

except ImportError:
    logger.warning("tiktoken not installed — using approximate token counts (chars/4)")

    def count_tokens(text: str) -> int:  # type: ignore[misc]
        return max(1, len(text) // 4)


# ── Constants ────────────────────────────────────────────────────────────────

DEFAULT_WINDOW_BUDGET = int(os.getenv("CONTEXT_WINDOW_BUDGET", "12000"))
SUMMARY_TRIGGER_RATIO = 0.75  # Summarise when usage exceeds 75 % of budget
SUMMARY_TARGET_TOKENS = 600   # Target size for the summary block


# ── Data ─────────────────────────────────────────────────────────────────────


@dataclass
class ContextMessage:
    """One turn in the conversation."""

    role: str  # user | assistant | system | summary
    content: str
    timestamp: float = field(default_factory=time.time)
    tokens: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.tokens == 0:
            self.tokens = count_tokens(self.content)


# ── Manager ──────────────────────────────────────────────────────────────────


class ContextWindowManager:
    """
    Manages a per-connection conversation context window.

    Usage::

        mgr = ContextWindowManager(budget=12000)
        mgr.add_user_message("Show me all patients older than 65")
        mgr.add_assistant_message("SELECT …", sql="SELECT …")
        context_str = mgr.get_context_string()   # for LLM prompts
        summary     = mgr.get_summary()           # condensed history
    """

    def __init__(self, budget: int = DEFAULT_WINDOW_BUDGET):
        self.budget = budget
        self.messages: List[ContextMessage] = []
        self._summary: Optional[str] = None  # Cached summary of evicted messages
        self._summary_tokens: int = 0
        self._total_tokens: int = 0

    # ── Public API ───────────────────────────────────────────────────────

    @property
    def total_tokens(self) -> int:
        return self._total_tokens + self._summary_tokens

    def add_user_message(self, content: str, **meta: Any) -> None:
        self._append("user", content, meta)

    def add_assistant_message(self, content: str, **meta: Any) -> None:
        self._append("assistant", content, meta)

    def add_system_message(self, content: str, **meta: Any) -> None:
        self._append("system", content, meta)

    def get_context_string(self, max_tokens: Optional[int] = None) -> str:
        """
        Return a formatted conversation string suitable for injection into
        an LLM prompt.  Optionally capped at *max_tokens*.
        """
        budget = max_tokens or self.budget
        parts: List[str] = []
        used = 0

        # Always include summary first
        if self._summary:
            parts.append(f"[Summary of earlier conversation]\n{self._summary}")
            used += self._summary_tokens

        # Walk messages newest-first so we prioritise recent context
        for msg in reversed(self.messages):
            if used + msg.tokens > budget:
                break
            parts.insert(len(parts) if not self._summary else 1, self._format_msg(msg))
            used += msg.tokens

        return "\n\n".join(parts)

    def get_summary(self) -> str:
        """Return the summary of older (evicted) conversation, or empty string."""
        return self._summary or ""

    def get_recent_messages(self, n: int = 10) -> List[Dict[str, Any]]:
        """Return the last *n* messages as plain dicts."""
        return [
            {"role": m.role, "content": m.content, "timestamp": m.timestamp}
            for m in self.messages[-n:]
        ]

    def clear(self) -> None:
        self.messages.clear()
        self._summary = None
        self._summary_tokens = 0
        self._total_tokens = 0

    # ── Internals ────────────────────────────────────────────────────────

    def _append(self, role: str, content: str, meta: Dict[str, Any]) -> None:
        msg = ContextMessage(role=role, content=content, metadata=meta)
        self.messages.append(msg)
        self._total_tokens += msg.tokens

        # Check if we need to summarise
        if self.total_tokens > self.budget * SUMMARY_TRIGGER_RATIO:
            self._maybe_summarise()

    def _maybe_summarise(self) -> None:
        """Evict older messages and replace them with a compressed summary."""
        if len(self.messages) < 4:
            return  # Not enough to summarise

        # Keep the most recent 3 messages; summarise everything older
        keep = 3
        to_summarise = self.messages[:-keep]
        if not to_summarise:
            return

        text_block = "\n".join(self._format_msg(m) for m in to_summarise)

        # Cap text_block to avoid blowing up the summarisation LLM call
        max_chars = 8000  # ~2000 tokens — safe for any model
        if len(text_block) > max_chars:
            text_block = text_block[-max_chars:]

        try:
            from llm.client import get_llm_client, get_model_name

            client = get_llm_client()
            resp = client.chat.completions.create(
                model=get_model_name(),
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Summarise the following database-query conversation into a concise "
                            "paragraph.  Preserve: which tables were discussed, key filters, "
                            "results counts, and any user preferences.  Be brief."
                        ),
                    },
                    {"role": "user", "content": text_block},
                ],
                temperature=0.2,
                max_tokens=SUMMARY_TARGET_TOKENS,
            )
            new_summary = (resp.choices[0].message.content or "").strip()
        except Exception as exc:
            logger.warning("Summarisation failed, falling back to truncation: %s", exc)
            # Fallback: just keep the last portion of text
            new_summary = text_block[-2000:]

        # Merge with any existing summary
        if self._summary:
            new_summary = f"{self._summary}\n\n{new_summary}"
            # If merged summary is itself too long, re-summarise (simple truncation)
            if count_tokens(new_summary) > SUMMARY_TARGET_TOKENS * 2:
                new_summary = new_summary[-(SUMMARY_TARGET_TOKENS * 4 * 4) :]

        self._summary = new_summary
        self._summary_tokens = count_tokens(new_summary)

        # Evict old messages
        evicted_tokens = sum(m.tokens for m in to_summarise)
        self._total_tokens -= evicted_tokens
        self.messages = self.messages[-keep:]

        logger.info(
            "Context summarised: evicted %d messages (%d tokens), summary=%d tokens, remaining=%d messages",
            len(to_summarise),
            evicted_tokens,
            self._summary_tokens,
            len(self.messages),
        )

    @staticmethod
    def _format_msg(msg: ContextMessage) -> str:
        label = {"user": "User", "assistant": "Assistant", "system": "System"}.get(
            msg.role, msg.role.title()
        )
        return f"{label}: {msg.content}"
