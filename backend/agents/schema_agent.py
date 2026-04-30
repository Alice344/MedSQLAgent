"""
Schema agent – selects relevant tables for a user query via RAG.

Wraps the existing ``llm.schema_retriever.retrieve_relevant_schema`` and
adds table-list formatting for the schema-explore intent.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from database.schema_storage import SchemaStorage
from llm.schema_retriever import retrieve_relevant_schema

from .base import AgentResult, AgentRole, BaseAgent, IntentType, TaskContext

logger = logging.getLogger(__name__)


class SchemaAgent(BaseAgent):
    role = AgentRole.SCHEMA

    def __init__(self, schema_storage: SchemaStorage, **kwargs: Any):
        super().__init__(**kwargs)
        self.schema_storage = schema_storage

    def run(self, ctx: TaskContext, **kwargs: Any) -> AgentResult:
        schema = self.schema_storage.load_schema(ctx.connection_id)
        if not schema:
            return AgentResult(success=False, error="Schema not found for this connection.")

        # For schema_explore, just return schema metadata
        if ctx.intent == IntentType.SCHEMA_EXPLORE:
            tables_summary = []
            for tbl in schema.get("tables", []):
                col_names = [c["name"] for c in tbl.get("columns", [])]
                tables_summary.append(
                    {
                        "full_name": tbl["full_name"],
                        "description": tbl.get("description", ""),
                        "column_count": len(col_names),
                        "columns": col_names[:20],  # Cap preview
                    }
                )
            ctx.add_message(
                "agent",
                f"Schema has {len(tables_summary)} tables.",
                agent=self.role.value,
            )
            return AgentResult(
                success=True,
                data={"tables": tables_summary, "total_tables": len(tables_summary)},
            )

        # For query / followup / export: RAG retrieval
        query_text = ctx.refined_query or ctx.user_query
        relevant = retrieve_relevant_schema(schema, query_text, top_k=5, fk_neighbor_depth=1)

        ctx.relevant_schema = relevant
        ctx.selected_tables = [t["full_name"] for t in relevant.get("tables", [])]
        ctx.formatted_schema = self.schema_storage.format_schema_for_llm(relevant)

        ctx.add_message(
            "agent",
            f"Selected {len(ctx.selected_tables)} relevant tables: {ctx.selected_tables}",
            agent=self.role.value,
        )

        logger.info(
            "SchemaAgent selected %d tables for query: %s",
            len(ctx.selected_tables),
            ctx.selected_tables,
        )

        return AgentResult(
            success=True,
            data={
                "selected_tables": ctx.selected_tables,
                "table_count": len(ctx.selected_tables),
            },
            next_agent=AgentRole.SQL_GENERATOR,
        )
