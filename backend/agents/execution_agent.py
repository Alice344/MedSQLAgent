"""
Execution agent – runs confirmed SQL against the live database connection.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List
from uuid import UUID

from database.connection import DatabaseConnection

from .base import AgentResult, AgentRole, BaseAgent, TaskContext

logger = logging.getLogger(__name__)


def _sanitize_rows(rows: Any) -> List[Dict[str, Any]]:
    """Convert pyodbc rows to JSON-safe dicts."""
    if not isinstance(rows, list):
        return rows
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            out.append(row)
            continue
        clean: Dict[str, Any] = {}
        for k, v in row.items():
            if isinstance(v, Decimal):
                clean[k] = float(v)
            elif isinstance(v, datetime):
                clean[k] = v.isoformat()
            elif isinstance(v, date):
                clean[k] = v.isoformat()
            elif isinstance(v, bytes):
                clean[k] = v.decode("utf-8", errors="replace")
            elif isinstance(v, UUID):
                clean[k] = str(v)
            else:
                clean[k] = v
        out.append(clean)
    return out


class ExecutionAgent(BaseAgent):
    """Runs SQL and returns results.  No LLM call needed."""

    role = AgentRole.EXECUTOR

    def __init__(self, **kwargs: Any):
        self.logger = logging.getLogger(f"agent.{self.role.value}")

    def run(self, ctx: TaskContext, **kwargs: Any) -> AgentResult:
        db_conn: DatabaseConnection | None = kwargs.get("db_connection")
        if db_conn is None:
            return AgentResult(success=False, error="No active database connection.")

        sql = ctx.generated_sql
        if not sql:
            return AgentResult(success=False, error="No SQL to execute.")

        try:
            results = _sanitize_rows(db_conn.execute_query(sql))
            row_count = len(results) if isinstance(results, list) else 1
        except Exception as exc:
            logger.exception("SQL execution failed")
            ctx.error = str(exc)
            ctx.add_message("agent", f"Execution error: {exc}", agent=self.role.value)
            return AgentResult(success=False, error=str(exc))

        ctx.execution_result = {"results": results, "row_count": row_count}
        ctx.add_message(
            "agent",
            f"Query returned {row_count} rows.",
            agent=self.role.value,
        )

        return AgentResult(
            success=True,
            data={"results": results, "row_count": row_count},
            next_agent=AgentRole.EXPLAINER,
        )
