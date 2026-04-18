"""
Intent classification agent.

Analyses the user message (plus optional conversation summary) and returns
a structured intent so the orchestrator knows which sub-agents to invoke.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from .base import AgentResult, AgentRole, BaseAgent, IntentType, TaskContext

logger = logging.getLogger(__name__)


class IntentAgent(BaseAgent):
    role = AgentRole.INTENT

    def run(self, ctx: TaskContext, **kwargs: Any) -> AgentResult:
        conversation_summary: str = kwargs.get("conversation_summary", "")

        system_prompt = (
            "You are an intent classifier for a medical-database SQL agent.\n"
            "Classify the user's message into exactly ONE of these intents:\n\n"
            '- "query"          – look up / analyse data (natural language → SQL)\n'
            '- "schema_explore" – see table or column information\n'
            '- "export"         – download / export data\n'
            '- "modify"         – INSERT, UPDATE, or DELETE data\n'
            '- "explain"        – explain a query, table, or concept\n'
            '- "followup"       – follow-up on a previous query (e.g. "show more", '
            '"filter by …", "what about …")\n'
            '- "clarify"        – request is too ambiguous to proceed\n'
            '- "general"        – general conversation, not about querying\n\n'
            "Return ONLY a JSON object:\n"
            '{"intent": "<intent>", "reasoning": "<brief explanation>", '
            '"refined_query": "<clarified version of the user request for downstream agents>"}'
        )

        user_msg = ctx.user_query
        if conversation_summary:
            user_msg = (
                f"[Conversation context]\n{conversation_summary}\n\n"
                f"[Current message]\n{ctx.user_query}"
            )

        raw = self._chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.0,
            max_tokens=250,
        )

        # Parse LLM response
        intent_str = "query"
        reasoning = ""
        refined = ctx.user_query
        try:
            cleaned = raw
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            parsed = json.loads(cleaned)
            intent_str = parsed.get("intent", "query")
            reasoning = parsed.get("reasoning", "")
            refined = parsed.get("refined_query", ctx.user_query)
        except (json.JSONDecodeError, AttributeError):
            logger.warning("IntentAgent returned non-JSON: %s", raw)
            reasoning = "Defaulted to query"

        try:
            intent = IntentType(intent_str)
        except ValueError:
            intent = IntentType.QUERY

        ctx.intent = intent
        ctx.refined_query = refined
        ctx.add_message(
            "agent",
            f"Intent classified: {intent.value} — {reasoning}",
            agent=self.role.value,
        )

        # Map intent → next agent
        next_agent = {
            IntentType.QUERY: AgentRole.SCHEMA,
            IntentType.SCHEMA_EXPLORE: AgentRole.SCHEMA,
            IntentType.EXPORT: AgentRole.SCHEMA,
            IntentType.MODIFY: AgentRole.SQL_GENERATOR,
            IntentType.EXPLAIN: AgentRole.EXPLAINER,
            IntentType.FOLLOWUP: AgentRole.SCHEMA,
            IntentType.CLARIFY: None,
            IntentType.GENERAL: None,
        }.get(intent)

        return AgentResult(
            success=True,
            data={
                "intent": intent.value,
                "reasoning": reasoning,
                "refined_query": refined,
            },
            next_agent=next_agent,
        )
