"""
Conversation orchestrator for the multi-agent SQL workflow.

This version keeps the control flow intentionally straightforward:

user message
  -> intent
  -> schema retrieval
  -> SQL generation
  -> validation
  -> [await confirmation] or [execute]
  -> explanation
  -> optional visualization
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from database.connection import DatabaseConnection
from database.schema_storage import SchemaStorage
from table_docs.table_doc_updater import update_table_docs_for_query

from context.manager import ContextWindowManager
from context.store import ConversationStore

from .base import AgentRole, AgentResult, IntentType, TaskContext, TaskStatus
from .execution_agent import ExecutionAgent
from .explanation_agent import ExplanationAgent
from .intent_agent import IntentAgent
from .schema_agent import SchemaAgent
from .sql_agent import SQLGeneratorAgent
from .validation_agent import ValidationAgent
from .visualization_agent import VisualizationAgent

logger = logging.getLogger(__name__)


class Orchestrator:
    """Coordinates the agents and keeps task state for HITL execution."""

    def __init__(self, schema_storage: SchemaStorage, conversation_store: ConversationStore):
        self.schema_storage = schema_storage
        self.conversation_store = conversation_store

        self.intent_agent = IntentAgent()
        self.schema_agent = SchemaAgent(schema_storage=schema_storage)
        self.sql_agent = SQLGeneratorAgent()
        self.validation_agent = ValidationAgent()
        self.execution_agent = ExecutionAgent()
        self.explanation_agent = ExplanationAgent()
        self.visualization_agent = VisualizationAgent()

        self._context_managers: Dict[str, ContextWindowManager] = {}
        self._pending_tasks: Dict[str, TaskContext] = {}
        self._completed_tasks: Dict[str, TaskContext] = {}

    # ── Public API ───────────────────────────────────────────────────────

    def handle_message(
        self,
        connection_id: str,
        user_message: str,
        db_connection: DatabaseConnection,
    ) -> Dict[str, Any]:
        conversation_id = self.conversation_store.get_or_create_conversation(connection_id)
        ctx_manager = self._get_context_manager(connection_id)

        ctx_manager.add_user_message(user_message)
        self.conversation_store.add_message(conversation_id, "user", user_message)

        ctx = TaskContext(
            connection_id=connection_id,
            user_query=user_message,
            status=TaskStatus.IN_PROGRESS,
        )
        ctx.add_message("user", user_message)

        conversation_summary = ctx_manager.get_summary()
        conversation_context = ctx_manager.get_context_string(max_tokens=4000)
        previous_sql = self._get_previous_sql(connection_id)
        similar_examples = self.conversation_store.find_similar_query_examples(
            user_message,
            limit=3,
            connection_id=connection_id,
        )

        intent_result = self.intent_agent.run(
            ctx,
            conversation_summary=conversation_summary,
        )
        if not intent_result.success:
            return self._error_response(ctx, intent_result.error or "Intent classification failed.")

        if ctx.intent == IntentType.GENERAL:
            reply = (
                "I can help with database questions, schema exploration, SQL generation, "
                "query execution, and result explanations."
            )
            ctx.add_message("assistant", reply, agent=AgentRole.ORCHESTRATOR.value)
            self._persist_assistant_message(connection_id, conversation_id, reply, ctx)
            return self._completed_response(ctx, explanation=reply)

        if ctx.intent == IntentType.CLARIFY:
            question = ctx.refined_query or "Could you clarify your request?"
            ctx.add_message("assistant", question, agent=AgentRole.ORCHESTRATOR.value)
            self._persist_assistant_message(connection_id, conversation_id, question, ctx)
            return {
                "status": "clarification_needed",
                "task_id": ctx.task_id,
                "refined_query": question,
                "agent_trace": self._agent_trace(ctx),
            }

        if ctx.intent == IntentType.EXPLAIN:
            explain_result = self.explanation_agent.run(ctx)
            if not explain_result.success:
                return self._error_response(ctx, explain_result.error or "Explanation failed.")
            reply = ctx.explanation or "Unable to generate explanation."
            self._persist_assistant_message(connection_id, conversation_id, reply, ctx)
            return self._completed_response(ctx, explanation=reply)

        schema_result = self.schema_agent.run(ctx)
        if not schema_result.success:
            return self._error_response(ctx, schema_result.error or "Schema retrieval failed.")

        if ctx.intent == IntentType.SCHEMA_EXPLORE:
            data = schema_result.data
            tables = data.get("tables", [])
            total_tables = data.get("total_tables", len(tables))
            summary_text = f"Found {total_tables} relevant tables."
            self._persist_assistant_message(connection_id, conversation_id, summary_text, ctx)
            return {
                "status": "schema_explore",
                "task_id": ctx.task_id,
                "tables": tables,
                "total_tables": total_tables,
                "agent_trace": self._agent_trace(ctx),
            }

        sql_result = self.sql_agent.run(
            ctx,
            conversation_context=conversation_context,
            previous_sql=previous_sql,
            similar_examples=similar_examples,
        )
        if not sql_result.success:
            return self._error_response(ctx, sql_result.error or "SQL generation failed.")

        validation_result = self.validation_agent.run(ctx)
        if not validation_result.success:
            return self._error_response(ctx, validation_result.error or "SQL validation failed.")

        ctx.status = TaskStatus.AWAITING_CONFIRMATION
        ctx.needs_confirmation = True
        ctx.confirmation_message = self._build_confirmation_message(validation_result)
        self._pending_tasks[ctx.task_id] = ctx

        review_msg = "I've generated SQL for your request. Please review or modify it before execution."
        self._persist_assistant_message(connection_id, conversation_id, review_msg, ctx)
        return {
            "status": "awaiting_confirmation",
            "task_id": ctx.task_id,
            "generated_sql": ctx.generated_sql,
            "confirmation_message": ctx.confirmation_message,
            "agent_trace": self._agent_trace(ctx),
        }

    def confirm_task(
        self,
        task_id: str,
        db_connection: DatabaseConnection,
        modified_sql: Optional[str] = None,
    ) -> Dict[str, Any]:
        ctx = self._pending_tasks.get(task_id)
        if not ctx:
            return {"status": "error", "error": f"Task '{task_id}' not found."}

        if modified_sql and modified_sql.strip():
            ctx.generated_sql = modified_sql.strip()
            ctx.add_message(
                "agent",
                "User provided modified SQL for execution.",
                agent=AgentRole.ORCHESTRATOR.value,
            )
            validation_result = self.validation_agent.run(ctx)
            if not validation_result.success:
                return {"status": "error", "error": validation_result.error or "Modified SQL validation failed."}

        ctx.status = TaskStatus.CONFIRMED
        conversation_id = self.conversation_store.get_or_create_conversation(ctx.connection_id)

        result = self._execute_and_finalize(
            ctx=ctx,
            db_connection=db_connection,
            conversation_id=conversation_id,
        )
        self._pending_tasks.pop(task_id, None)
        return result

    def reject_task(self, task_id: str, reason: str = "") -> Dict[str, Any]:
        ctx = self._pending_tasks.pop(task_id, None)
        if not ctx:
            return {"status": "error", "error": f"Task '{task_id}' not found."}

        ctx.status = TaskStatus.REJECTED
        note = reason.strip() or "User rejected the generated SQL."
        ctx.add_message("assistant", note, agent=AgentRole.ORCHESTRATOR.value)

        conversation_id = self.conversation_store.get_or_create_conversation(ctx.connection_id)
        self._persist_assistant_message(ctx.connection_id, conversation_id, note, ctx)
        return {
            "status": "completed",
            "task_id": ctx.task_id,
            "explanation": note,
            "agent_trace": self._agent_trace(ctx),
        }

    def visualize_task(self, task_id: str) -> Dict[str, Any]:
        ctx = self._completed_tasks.get(task_id)
        if not ctx:
            return {"status": "error", "error": f"Task '{task_id}' not found or has no results."}

        viz_result = self.visualization_agent.run(ctx)
        if not viz_result.success:
            return {"status": "error", "error": viz_result.error or "Visualization failed."}

        return {
            "status": "completed",
            "task_id": ctx.task_id,
            "visualization": ctx.visualization_config,
            "agent_trace": self._agent_trace(ctx),
        }

    def get_conversation_history(self, connection_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        conversation_id = self.conversation_store.get_or_create_conversation(connection_id)
        return self.conversation_store.get_messages(conversation_id, limit=limit)

    def get_query_history(self, connection_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        return self.conversation_store.get_query_history(connection_id, limit=limit)

    def clear_conversation(self, connection_id: str) -> None:
        self.conversation_store.clear_conversation(connection_id)
        self._context_managers.pop(connection_id, None)

        pending_to_remove = [
            task_id for task_id, ctx in self._pending_tasks.items() if ctx.connection_id == connection_id
        ]
        for task_id in pending_to_remove:
            self._pending_tasks.pop(task_id, None)

        completed_to_remove = [
            task_id for task_id, ctx in self._completed_tasks.items() if ctx.connection_id == connection_id
        ]
        for task_id in completed_to_remove:
            self._completed_tasks.pop(task_id, None)

    def new_conversation(self, connection_id: str) -> str:
        self._context_managers.pop(connection_id, None)
        return self.conversation_store.new_conversation(connection_id)

    # ── Internals ────────────────────────────────────────────────────────

    def _execute_and_finalize(
        self,
        ctx: TaskContext,
        db_connection: DatabaseConnection,
        conversation_id: str,
    ) -> Dict[str, Any]:
        execution_result = self.execution_agent.run(ctx, db_connection=db_connection)
        if not execution_result.success:
            return self._error_response(ctx, execution_result.error or "Execution failed.")

        explain_result = self.explanation_agent.run(ctx)
        if not explain_result.success:
            return self._error_response(ctx, explain_result.error or "Explanation failed.")

        ctx.status = TaskStatus.COMPLETED
        self._completed_tasks[ctx.task_id] = ctx

        self.conversation_store.add_query_history(
            connection_id=ctx.connection_id,
            conversation_id=conversation_id,
            task_id=ctx.task_id,
            user_query=ctx.user_query,
            generated_sql=ctx.generated_sql,
            row_count=(ctx.execution_result or {}).get("row_count"),
            status="completed",
            metadata={
                "selected_tables": ctx.selected_tables,
                "intent": ctx.intent.value if ctx.intent else None,
            },
        )

        schema = self.schema_storage.load_schema(ctx.connection_id)
        if schema and ctx.generated_sql:
            try:
                update_table_docs_for_query(
                    schema=schema,
                    sql_query=ctx.generated_sql,
                    natural_language_query=ctx.user_query,
                )
            except Exception as exc:
                logger.warning("Failed to update table docs for task %s: %s", ctx.task_id, exc)

        assistant_text = ctx.explanation or "Query completed successfully."
        self._persist_assistant_message(ctx.connection_id, conversation_id, assistant_text, ctx)

        return self._completed_response(
            ctx,
            generated_sql=ctx.generated_sql,
            explanation=ctx.explanation,
            results=(ctx.execution_result or {}).get("results"),
            row_count=(ctx.execution_result or {}).get("row_count"),
            visualization=ctx.visualization_config,
        )

    def _completed_response(self, ctx: TaskContext, **extra: Any) -> Dict[str, Any]:
        payload = {
            "status": "completed",
            "task_id": ctx.task_id,
            "agent_trace": self._agent_trace(ctx),
        }
        payload.update({k: v for k, v in extra.items() if v is not None})
        return payload

    def _error_response(self, ctx: TaskContext, error: str) -> Dict[str, Any]:
        ctx.status = TaskStatus.FAILED
        ctx.error = error
        return {
            "status": "error",
            "task_id": ctx.task_id,
            "error": error,
            "agent_trace": self._agent_trace(ctx),
        }

    def _persist_assistant_message(
        self,
        connection_id: str,
        conversation_id: str,
        content: str,
        ctx: TaskContext,
    ) -> None:
        manager = self._get_context_manager(connection_id)
        manager.add_assistant_message(content, task_id=ctx.task_id)
        self.conversation_store.add_message(
            conversation_id,
            "assistant",
            content,
            agent=AgentRole.ORCHESTRATOR.value,
            metadata={"task_id": ctx.task_id},
        )

    def _get_context_manager(self, connection_id: str) -> ContextWindowManager:
        manager = self._context_managers.get(connection_id)
        if manager is None:
            manager = ContextWindowManager()
            self._context_managers[connection_id] = manager
        return manager

    def _get_previous_sql(self, connection_id: str) -> Optional[str]:
        history = self.conversation_store.get_query_history(connection_id, limit=1)
        if not history:
            return None
        sql = history[0].get("generated_sql")
        return str(sql) if sql else None

    @staticmethod
    def _build_confirmation_message(validation_result: AgentResult) -> str:
        base = "Please review the generated SQL before execution. You can confirm it as-is or modify it first."
        extra = (validation_result.confirmation_message or "").strip()
        if extra:
            return f"{base}\n\n{extra}"
        return base

    @staticmethod
    def _agent_trace(ctx: TaskContext) -> List[Dict[str, str]]:
        trace: List[Dict[str, str]] = []
        for msg in ctx.messages:
            if msg.agent:
                trace.append({"agent": msg.agent, "content": msg.content})
        return trace
