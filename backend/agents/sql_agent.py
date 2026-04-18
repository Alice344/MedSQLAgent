"""
SQL-generator agent – converts natural language + schema into T-SQL.

Wraps the existing ``llm.sql_generator.SQLGenerator`` while adding
conversation-aware prompting when prior queries are available.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional

from .base import AgentResult, AgentRole, BaseAgent, TaskContext

logger = logging.getLogger(__name__)

SQL_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


class SQLGeneratorAgent(BaseAgent):
    role = AgentRole.SQL_GENERATOR

    def run(self, ctx: TaskContext, **kwargs: Any) -> AgentResult:
        conversation_context: str = kwargs.get("conversation_context", "")
        previous_sql: Optional[str] = kwargs.get("previous_sql", None)

        system_prompt = (
            "You are an expert SQL developer specialising in Microsoft SQL Server (T-SQL).\n"
            "Your task is to convert natural language queries into accurate, optimised SQL.\n\n"
            "Rules:\n"
            "1. Always use proper T-SQL syntax.\n"
            "2. CRITICAL: Use table and column names EXACTLY as in the schema — do NOT invent names.\n"
            "3. CRITICAL: Always qualify tables with their schema prefix (e.g. dbo.PatientDim).\n"
            "4. Include proper JOINs based on foreign-key relationships.\n"
            "5. Use appropriate WHERE, aggregations, and ORDER BY.\n"
            "6. Return ONLY the SQL query — no markdown, no explanation.\n"
            "7. If the query is ambiguous, make reasonable assumptions using only the provided schema.\n"
            "8. For follow-up queries, build on the previous SQL shown in the conversation.\n"
        )

        # Build user message with optional prior context
        parts: List[str] = []
        if conversation_context:
            parts.append(f"[Prior conversation]\n{conversation_context}\n")
        if previous_sql:
            parts.append(f"[Previous SQL query]\n{previous_sql}\n")
        parts.append(
            f"Database Schema (use ONLY these table/column names):\n{ctx.formatted_schema}\n"
        )
        parts.append(f"User Request:\n{ctx.refined_query or ctx.user_query}")
        parts.append("\nGenerate the SQL query:")

        user_prompt = "\n".join(parts)

        raw = self._chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model=SQL_MODEL,
            temperature=0.1,
            max_tokens=1500,
        )

        sql_query = self._clean_sql(raw)
        if not sql_query:
            return AgentResult(success=False, error="LLM returned empty SQL.")

        ctx.generated_sql = sql_query
        ctx.add_message("agent", f"Generated SQL:\n{sql_query}", agent=self.role.value)

        return AgentResult(
            success=True,
            data={"sql": sql_query},
            next_agent=AgentRole.VALIDATOR,
        )

    # ── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _clean_sql(raw: str) -> str:
        """Strip markdown fences and whitespace from LLM output."""
        sql = raw.strip()
        fence = re.match(
            r"^\s*```(?:sql)?\s*\r?\n?(.*?)\r?\n?```\s*$", sql, re.DOTALL | re.IGNORECASE
        )
        if fence:
            return fence.group(1).strip()
        for prefix in ("```sql", "```"):
            if sql.startswith(prefix):
                sql = sql[len(prefix) :]
        if sql.endswith("```"):
            sql = sql[: -3]
        return sql.strip()
