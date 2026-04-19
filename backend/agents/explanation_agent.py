"""
Explanation agent – produces a human-readable summary of a SQL query
and/or its results.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from .base import AgentResult, AgentRole, BaseAgent, IntentType, TaskContext

logger = logging.getLogger(__name__)


class ExplanationAgent(BaseAgent):
    role = AgentRole.EXPLAINER

    def run(self, ctx: TaskContext, **kwargs: Any) -> AgentResult:
        sql = ctx.generated_sql or ""
        results = ctx.execution_result or {}
        row_count = results.get("row_count", 0)
        sample_rows = (results.get("results") or [])[:5]

        # Different prompts depending on intent
        if ctx.intent == IntentType.EXPLAIN:
            # User explicitly asked for an explanation
            system_prompt = (
                "You are a helpful database assistant. "
                "Explain the following SQL query in simple, non-technical terms. "
                "Also mention what tables and columns are involved."
            )
            user_prompt = f"Explain this SQL:\n{ctx.user_query}"
        else:
            system_prompt = (
                "You are a helpful database assistant. "
                "Briefly explain what the SQL query does and summarise the results. "
                "Keep it concise — at most 2-3 sentences."
            )
            parts = [f"SQL Query:\n{sql}"]
            if sample_rows:
                parts.append(f"Result preview ({row_count} total rows):\n{json.dumps(sample_rows[:3], default=str)}")
            user_prompt = "\n\n".join(parts)

        try:
            explanation = self._chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=400,
            )
        except Exception as exc:
            logger.error("ExplanationAgent failed: %s", exc)
            explanation = "Unable to generate explanation."

        ctx.explanation = explanation
        ctx.add_message("agent", explanation, agent=self.role.value)

        return AgentResult(
            success=True,
            data={"explanation": explanation},
        )
