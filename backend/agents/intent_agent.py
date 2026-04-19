"""
Intent classification agent (with optional merged table selection).

When called with a ``table_catalog`` kwarg, this agent classifies intent AND
selects the most relevant tables in a **single** LLM call — eliminating a
separate SchemaAgent round-trip.
"""
from __future__ import annotations

import json
import logging
from typing import Any, List, Optional

from .base import AgentResult, AgentRole, BaseAgent, IntentType, TaskContext

logger = logging.getLogger(__name__)


class IntentAgent(BaseAgent):
    role = AgentRole.INTENT

    def run(self, ctx: TaskContext, **kwargs: Any) -> AgentResult:
        conversation_summary: str = kwargs.get("conversation_summary", "")
        table_catalog: str = kwargs.get("table_catalog", "")
        top_k: int = kwargs.get("top_k", 5)

        include_tables = bool(table_catalog)

        system_prompt = (
            self._merged_prompt(top_k) if include_tables else self._basic_prompt()
        )

        # Build user message
        parts: List[str] = []
        if conversation_summary:
            parts.append(f"[Conversation context]\n{conversation_summary}")
        if table_catalog:
            parts.append(f"[Available database tables]\n{table_catalog}")
        parts.append(f"[User message]\n{ctx.user_query}")
        user_msg = "\n\n".join(parts)

        raw = self._chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.0,
            max_tokens=500 if include_tables else 250,
        )

        # ── Parse response ───────────────────────────────────────────────
        intent_str = "query"
        reasoning = ""
        refined = ctx.user_query
        selected_tables: List[str] = []

        try:
            cleaned = raw
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            parsed = json.loads(cleaned)
            intent_str = parsed.get("intent", "query")
            reasoning = parsed.get("reasoning", "")
            refined = parsed.get("refined_query", ctx.user_query)
            if include_tables:
                selected_tables = parsed.get("selected_tables", [])
                if not isinstance(selected_tables, list):
                    selected_tables = []
        except (json.JSONDecodeError, AttributeError):
            logger.warning("IntentAgent returned non-JSON: %s", raw)
            reasoning = "Defaulted to query"

        try:
            intent = IntentType(intent_str)
        except ValueError:
            intent = IntentType.QUERY

        ctx.intent = intent
        ctx.refined_query = refined
        if selected_tables:
            ctx.selected_tables = selected_tables

        trace_msg = f"Intent: {intent.value} — {reasoning}"
        if selected_tables:
            trace_msg += f"\nSelected tables: {selected_tables}"
        ctx.add_message("agent", trace_msg, agent=self.role.value)

        # ── Determine next agent ─────────────────────────────────────────
        if include_tables and selected_tables:
            # Tables already selected → skip SchemaAgent, go straight to SQL
            next_map = {
                IntentType.QUERY: AgentRole.SQL_GENERATOR,
                IntentType.EXPORT: AgentRole.SQL_GENERATOR,
                IntentType.MODIFY: AgentRole.SQL_GENERATOR,
                IntentType.FOLLOWUP: AgentRole.SQL_GENERATOR,
                IntentType.VISUALIZE: AgentRole.SQL_GENERATOR,
                IntentType.SCHEMA_EXPLORE: AgentRole.SCHEMA,
                IntentType.EXPLAIN: AgentRole.EXPLAINER,
                IntentType.CLARIFY: None,
                IntentType.GENERAL: None,
            }
        else:
            next_map = {
                IntentType.QUERY: AgentRole.SCHEMA,
                IntentType.SCHEMA_EXPLORE: AgentRole.SCHEMA,
                IntentType.EXPORT: AgentRole.SCHEMA,
                IntentType.MODIFY: AgentRole.SQL_GENERATOR,
                IntentType.EXPLAIN: AgentRole.EXPLAINER,
                IntentType.FOLLOWUP: AgentRole.SCHEMA,
                IntentType.VISUALIZE: AgentRole.SCHEMA,
                IntentType.CLARIFY: None,
                IntentType.GENERAL: None,
            }

        return AgentResult(
            success=True,
            data={
                "intent": intent.value,
                "reasoning": reasoning,
                "refined_query": refined,
                "selected_tables": selected_tables,
            },
            next_agent=next_map.get(intent),
        )

    # ── Prompt helpers ───────────────────────────────────────────────────

    @staticmethod
    def _merged_prompt(top_k: int) -> str:
        return (
            "You are an intent classifier and table selector for a medical-database SQL agent.\n\n"
            "Given the user's message and a database table catalog, you must:\n"
            "1. Classify the user's intent into exactly ONE category\n"
            f"2. Select up to {top_k} most relevant tables from the catalog\n"
            "3. Provide a refined/clarified version of the request\n\n"
            "Intent categories:\n"
            '- "query"          – look up / analyse data (needs SQL)\n'
            '- "visualize"      – create charts or visualizations from data\n'
            '- "schema_explore" – browse table or column information\n'
            '- "export"         – download / export data\n'
            '- "modify"         – INSERT, UPDATE, or DELETE data\n'
            '- "explain"        – explain a previous query or concept\n'
            '- "followup"       – follow-up on a previous query\n'
            '- "clarify"        – request is too ambiguous\n'
            '- "general"        – general conversation, not about data\n\n'
            "Return ONLY a JSON object (no markdown fences):\n"
            '{\n'
            '  "intent": "<intent>",\n'
            '  "reasoning": "<brief explanation>",\n'
            '  "refined_query": "<clarified version of the request>",\n'
            '  "selected_tables": ["schema.Table1", "schema.Table2"]\n'
            '}\n\n'
            "IMPORTANT: selected_tables must contain EXACT table names from the catalog."
        )

    @staticmethod
    def _basic_prompt() -> str:
        return (
            "You are an intent classifier for a medical-database SQL agent.\n"
            "Classify the user's message into exactly ONE of these intents:\n\n"
            '- "query"          – look up / analyse data (natural language → SQL)\n'
            '- "visualize"      – create charts or visualizations from data\n'
            '- "schema_explore" – see table or column information\n'
            '- "export"         – download / export data\n'
            '- "modify"         – INSERT, UPDATE, or DELETE data\n'
            '- "explain"        – explain a query, table, or concept\n'
            '- "followup"       – follow-up on a previous query\n'
            '- "clarify"        – request is too ambiguous to proceed\n'
            '- "general"        – general conversation, not about querying\n\n'
            "Return ONLY a JSON object:\n"
            '{"intent": "<intent>", "reasoning": "<brief explanation>", '
            '"refined_query": "<clarified version of the user request>"}'
        )
