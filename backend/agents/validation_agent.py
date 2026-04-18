"""
Validation agent – reviews generated SQL for safety and correctness
before it reaches the user for confirmation.

Checks performed:
- Dangerous operations (DROP, TRUNCATE, ALTER, DELETE without WHERE, …)
- DML detection (INSERT / UPDATE / DELETE flagged for mandatory confirmation)
- Basic syntax heuristics
- Table-name cross-check against selected schema
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Set

from .base import AgentResult, AgentRole, BaseAgent, TaskContext

logger = logging.getLogger(__name__)

# Patterns that ALWAYS require human confirmation
_DANGEROUS_PATTERNS: List[re.Pattern] = [
    re.compile(r"\bDROP\b", re.IGNORECASE),
    re.compile(r"\bTRUNCATE\b", re.IGNORECASE),
    re.compile(r"\bALTER\b", re.IGNORECASE),
    re.compile(r"\bEXEC(?:UTE)?\b", re.IGNORECASE),
    re.compile(r"\bxp_", re.IGNORECASE),
    re.compile(r"\bsp_", re.IGNORECASE),
]

# DML that modifies data – needs confirmation but isn't "dangerous"
_DML_PATTERNS: List[re.Pattern] = [
    re.compile(r"\bINSERT\b", re.IGNORECASE),
    re.compile(r"\bUPDATE\b", re.IGNORECASE),
    re.compile(r"\bDELETE\b", re.IGNORECASE),
    re.compile(r"\bMERGE\b", re.IGNORECASE),
]


class ValidationAgent(BaseAgent):
    """
    Stateless agent — no LLM call needed.  Pure rule-based validation.
    """

    role = AgentRole.VALIDATOR

    def __init__(self, **kwargs: Any):
        # Skip OpenAI init — this agent doesn't call the LLM
        self.logger = logging.getLogger(f"agent.{self.role.value}")

    def run(self, ctx: TaskContext, **kwargs: Any) -> AgentResult:
        sql = ctx.generated_sql or ""
        warnings: List[str] = []
        risk_level = "low"  # low | medium | high | critical

        # 1. Empty check
        if not sql.strip():
            return AgentResult(
                success=False,
                error="No SQL to validate.",
            )

        # 2. Dangerous patterns
        for pat in _DANGEROUS_PATTERNS:
            if pat.search(sql):
                risk_level = "critical"
                warnings.append(f"⚠️  Dangerous operation detected: {pat.pattern}")

        # 3. DML patterns
        is_dml = False
        for pat in _DML_PATTERNS:
            if pat.search(sql):
                is_dml = True
                if risk_level != "critical":
                    risk_level = "high"
                warnings.append(f"Data-modifying operation: {pat.pattern}")

        # 4. DELETE / UPDATE without WHERE
        if re.search(r"\bDELETE\b", sql, re.IGNORECASE) and not re.search(
            r"\bWHERE\b", sql, re.IGNORECASE
        ):
            risk_level = "critical"
            warnings.append("⚠️  DELETE without WHERE clause — will affect ALL rows!")

        if re.search(r"\bUPDATE\b", sql, re.IGNORECASE) and not re.search(
            r"\bWHERE\b", sql, re.IGNORECASE
        ):
            risk_level = "critical"
            warnings.append("⚠️  UPDATE without WHERE clause — will affect ALL rows!")

        # 5. Cross-check table names against selected schema
        if ctx.selected_tables:
            known: Set[str] = set(ctx.selected_tables)
            # Try to extract table references from SQL (simple heuristic)
            from_matches = re.findall(
                r"\bFROM\s+(\[?[\w.]+\]?)", sql, re.IGNORECASE
            )
            join_matches = re.findall(
                r"\bJOIN\s+(\[?[\w.]+\]?)", sql, re.IGNORECASE
            )
            referenced = set(from_matches + join_matches)
            # Normalise brackets
            referenced = {t.strip("[]") for t in referenced}
            unknown = referenced - known
            if unknown:
                if risk_level in ("low",):
                    risk_level = "medium"
                warnings.append(
                    f"SQL references tables not in the selected schema: {unknown}"
                )

        # 6. Very large result risk (SELECT without TOP / LIMIT heuristic)
        if (
            sql.strip().upper().startswith("SELECT")
            and "TOP" not in sql.upper()
            and "OFFSET" not in sql.upper()
        ):
            if risk_level == "low":
                risk_level = "medium"
            warnings.append(
                "Query has no TOP / OFFSET clause — could return a large result set."
            )

        # Build result
        needs_confirm = risk_level in ("high", "critical") or is_dml
        confirm_msg = None
        if needs_confirm:
            lines = ["Please review the SQL before execution:"]
            for w in warnings:
                lines.append(f"  • {w}")
            lines.append(f"\nRisk level: **{risk_level}**")
            confirm_msg = "\n".join(lines)

        validation = {
            "risk_level": risk_level,
            "is_dml": is_dml,
            "warnings": warnings,
        }
        ctx.validation_result = validation
        ctx.add_message(
            "agent",
            f"Validation: risk={risk_level}, warnings={len(warnings)}",
            agent=self.role.value,
        )

        return AgentResult(
            success=True,
            data=validation,
            needs_confirmation=needs_confirm,
            confirmation_message=confirm_msg,
            next_agent=AgentRole.EXECUTOR if not needs_confirm else None,
        )
