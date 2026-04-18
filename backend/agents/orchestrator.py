"""
Orchestrator – the central coordinator of the multi-agent pipeline.

Responsibilities
----------------
1. Accept a user message and route it through sub-agents.
2. Maintain per-connection context windows (token-managed).
3. Persist conversations and query history to SQLite.
4. Pause the pipeline for human-in-the-loop (HITL) confirmation when required.
5. Resume execution after the user confirms / rejects / modifies.

Pipeline (for a typical QUERY intent)
--------------------------------------
User msg → IntentAgent → SchemaAgent → SQLGeneratorAgent → ValidationAgent
  → [HITL pause if needed] → ExecutionAgent → ExplanationAgent → Response
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from database.connection import DatabaseConnection
from database.schema_storage import SchemaStorage

from context.manager import ContextWindowManager
from context.store import ConversationStore

from .base import AgentResult, AgentRole, IntentType, TaskContext, TaskStatus
from .intent_agent import IntentAgent
from .schema_agent import SchemaAgent
from .sql_agent import SQLGeneratorAgent
from .validation_agent import ValidationAgent
from .execution_agent import ExecutionAgent
from .explanation_agent import ExplanationAgent

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Main entry-point for the multi-agent system.

    Instantiate once at app startup; call ``handle_message`` for each user turn.
    """

    def __init__(
        self,
        schema_storage: SchemaStorage,
        conversation_store: Optional[ConversationStore] = None,
        context_budget: int = 12_000,
    ):
        self.schema_storage = schema_storage
        self.store = conversation_store or ConversationStore()

        # Per-connection context managers (connection_id → ContextWindowManager)
        self._contexts: Dict[str, ContextWindowManager] = {}

        # Pending tasks awaiting human confirmation (task_id → TaskContext)
        self.pending_tasks: Dict[str, TaskContext] = {}

        self.context_budget = context_budget

        # Lazy-init agents (created on first use so OPENAI_API_KEY can be set later)
        self._agents: Dict[AgentRole, Any] = {}

    # ── Agent factory ────────────────────────────────────────────────────

    def _get_agent(self, role: AgentRole):
        if role not in self._agents:
            if role == AgentRole.INTENT:
                self._agents[role] = IntentAgent()
            elif role == AgentRole.SCHEMA:
                self._agents[role] = SchemaAgent(schema_storage=self.schema_storage)
            elif role == AgentRole.SQL_GENERATOR:
                self._agents[role] = SQLGeneratorAgent()
            elif role == AgentRole.VALIDATOR:
                self._agents[role] = ValidationAgent()
            elif role == AgentRole.EXECUTOR:
                self._agents[role] = ExecutionAgent()
            elif role == AgentRole.EXPLAINER:
                self._agents[role] = ExplanationAgent()
            else:
                raise ValueError(f"Unknown agent role: {role}")
        return self._agents[role]

    # ── Context helpers ──────────────────────────────────────────────────

    def _ctx_mgr(self, connection_id: str) -> ContextWindowManager:
        if connection_id not in self._contexts:
            self._contexts[connection_id] = ContextWindowManager(budget=self.context_budget)
        return self._contexts[connection_id]

    def _previous_sql(self, connection_id: str) -> Optional[str]:
        """Return the last generated SQL for follow-up queries."""
        history = self.store.get_query_history(connection_id, limit=1)
        if history and history[0].get("generated_sql"):
            return history[0]["generated_sql"]
        return None

    # ── Main entry point ─────────────────────────────────────────────────

    def handle_message(
        self,
        connection_id: str,
        user_message: str,
        db_connection: Optional[DatabaseConnection] = None,
    ) -> Dict[str, Any]:
        """
        Process a user message end-to-end (or up to an HITL pause).

        Returns a dict with:
          - status: completed | awaiting_confirmation | clarification_needed | error
          - task_id
          - generated_sql, results, explanation (when available)
          - confirmation_message (when HITL pause)
          - agent_trace: list of agent messages
        """
        ctx = TaskContext(connection_id=connection_id, user_query=user_message)
        ctx.status = TaskStatus.IN_PROGRESS

        # Record user message in context window + persistent store
        cm = self._ctx_mgr(connection_id)
        cm.add_user_message(user_message)
        conv_id = self.store.get_or_create_conversation(connection_id)
        self.store.add_message(conv_id, "user", user_message)

        # 1. Intent classification
        try:
            intent_result = self._run_agent(
                AgentRole.INTENT,
                ctx,
                conversation_summary=cm.get_summary(),
            )
        except Exception as exc:
            return self._error_response(ctx, f"Intent classification failed: {exc}")

        if not intent_result.success:
            return self._error_response(ctx, intent_result.error or "Intent classification failed")

        # Handle non-pipeline intents immediately
        if ctx.intent in (IntentType.CLARIFY, IntentType.GENERAL):
            reply = intent_result.data.get("refined_query", "Could you clarify your request?")
            cm.add_assistant_message(reply)
            self.store.add_message(conv_id, "assistant", reply)
            ctx.status = TaskStatus.COMPLETED
            return self._build_response(ctx, status="clarification_needed")

        # Handle schema_explore directly
        if ctx.intent == IntentType.SCHEMA_EXPLORE:
            schema_result = self._run_agent(AgentRole.SCHEMA, ctx)
            if schema_result.success:
                reply = f"Found {schema_result.data.get('total_tables', 0)} tables."
                cm.add_assistant_message(reply)
                self.store.add_message(conv_id, "assistant", reply)
                ctx.status = TaskStatus.COMPLETED
                return self._build_response(ctx, extra_data=schema_result.data)
            return self._error_response(ctx, schema_result.error or "Schema retrieval failed")

        # Handle explain intent
        if ctx.intent == IntentType.EXPLAIN:
            explain_result = self._run_agent(AgentRole.EXPLAINER, ctx)
            reply = ctx.explanation or "Unable to generate explanation."
            cm.add_assistant_message(reply)
            self.store.add_message(conv_id, "assistant", reply)
            ctx.status = TaskStatus.COMPLETED
            return self._build_response(ctx)

        # 2. Schema retrieval (for query/followup/export/modify)
        schema_result = self._run_agent(AgentRole.SCHEMA, ctx)
        if not schema_result.success:
            return self._error_response(ctx, schema_result.error or "Schema retrieval failed")

        # 3. SQL generation
        sql_result = self._run_agent(
            AgentRole.SQL_GENERATOR,
            ctx,
            conversation_context=cm.get_context_string(max_tokens=3000),
            previous_sql=self._previous_sql(connection_id),
        )
        if not sql_result.success:
            return self._error_response(ctx, sql_result.error or "SQL generation failed")

        # 4. Validation
        val_result = self._run_agent(AgentRole.VALIDATOR, ctx)
        if not val_result.success:
            return self._error_response(ctx, val_result.error or "Validation failed")

        # 5. Check if human confirmation is needed
        if val_result.needs_confirmation:
            ctx.status = TaskStatus.AWAITING_CONFIRMATION
            ctx.needs_confirmation = True
            ctx.confirmation_message = val_result.confirmation_message
            self.pending_tasks[ctx.task_id] = ctx
            # Store the db_connection reference for later
            if db_connection:
                ctx.add_message("system", "__db_ref__", metadata={"_db_ref": True})
            return self._build_response(ctx, status="awaiting_confirmation")

        # 6. Execute (no confirmation needed — low-risk SELECT)
        if db_connection is None:
            return self._error_response(ctx, "No active database connection")

        return self._execute_and_explain(ctx, db_connection, conv_id, cm)

    # ── Confirmation handlers ────────────────────────────────────────────

    def confirm_task(
        self,
        task_id: str,
        db_connection: Optional[DatabaseConnection] = None,
        modified_sql: Optional[str] = None,
    ) -> Dict[str, Any]:
        """User confirms (or modifies) a pending task → execute it."""
        ctx = self.pending_tasks.pop(task_id, None)
        if ctx is None:
            return {"status": "error", "error": "Task not found or already processed."}

        if modified_sql:
            ctx.generated_sql = modified_sql
            ctx.add_message("user", f"Modified SQL to:\n{modified_sql}")

        ctx.status = TaskStatus.CONFIRMED
        cm = self._ctx_mgr(ctx.connection_id)
        conv_id = self.store.get_or_create_conversation(ctx.connection_id)

        if db_connection is None:
            return self._error_response(ctx, "No active database connection")

        return self._execute_and_explain(ctx, db_connection, conv_id, cm)

    def reject_task(self, task_id: str, reason: str = "") -> Dict[str, Any]:
        """User rejects a pending task."""
        ctx = self.pending_tasks.pop(task_id, None)
        if ctx is None:
            return {"status": "error", "error": "Task not found or already processed."}

        ctx.status = TaskStatus.REJECTED
        cm = self._ctx_mgr(ctx.connection_id)
        conv_id = self.store.get_or_create_conversation(ctx.connection_id)

        reply = "Query cancelled by user."
        if reason:
            reply += f" Reason: {reason}"
        cm.add_assistant_message(reply)
        self.store.add_message(conv_id, "assistant", reply)

        self.store.add_query_history(
            connection_id=ctx.connection_id,
            user_query=ctx.user_query,
            generated_sql=ctx.generated_sql,
            status="rejected",
            conversation_id=conv_id,
            task_id=ctx.task_id,
        )

        return self._build_response(ctx, status="rejected")

    # ── History / context endpoints ──────────────────────────────────────

    def get_conversation_history(
        self, connection_id: str, limit: int = 50
    ) -> Dict[str, Any]:
        conv_id = self.store.get_or_create_conversation(connection_id)
        messages = self.store.get_messages(conv_id, limit=limit)
        return {"conversation_id": conv_id, "messages": messages}

    def get_query_history(
        self, connection_id: str, limit: int = 20
    ) -> list:
        return self.store.get_query_history(connection_id, limit=limit)

    def clear_conversation(self, connection_id: str) -> None:
        self.store.clear_conversation(connection_id)
        if connection_id in self._contexts:
            self._contexts[connection_id].clear()

    def new_conversation(self, connection_id: str) -> str:
        """Start a fresh conversation thread (keeps history of old ones)."""
        if connection_id in self._contexts:
            self._contexts[connection_id].clear()
        return self.store.new_conversation(connection_id)

    # ── Internals ────────────────────────────────────────────────────────

    def _run_agent(self, role: AgentRole, ctx: TaskContext, **kwargs: Any) -> AgentResult:
        agent = self._get_agent(role)
        logger.info("Running %s agent for task %s", role.value, ctx.task_id)
        return agent.run(ctx, **kwargs)

    def _execute_and_explain(
        self,
        ctx: TaskContext,
        db_connection: DatabaseConnection,
        conv_id: str,
        cm: ContextWindowManager,
    ) -> Dict[str, Any]:
        """Execute SQL and get explanation — shared by handle_message and confirm_task."""
        exec_result = self._run_agent(AgentRole.EXECUTOR, ctx, db_connection=db_connection)
        if not exec_result.success:
            self.store.add_query_history(
                connection_id=ctx.connection_id,
                user_query=ctx.user_query,
                generated_sql=ctx.generated_sql,
                status="failed",
                error=exec_result.error,
                conversation_id=conv_id,
                task_id=ctx.task_id,
            )
            return self._error_response(ctx, exec_result.error or "Execution failed")

        # Explanation
        self._run_agent(AgentRole.EXPLAINER, ctx)

        # Update context window
        assistant_reply = (
            f"SQL: {ctx.generated_sql}\n"
            f"Rows: {exec_result.data.get('row_count', 0)}\n"
            f"{ctx.explanation or ''}"
        )
        cm.add_assistant_message(assistant_reply, sql=ctx.generated_sql)

        # Persist
        self.store.add_message(conv_id, "assistant", assistant_reply, agent="orchestrator")
        self.store.add_query_history(
            connection_id=ctx.connection_id,
            user_query=ctx.user_query,
            generated_sql=ctx.generated_sql,
            row_count=exec_result.data.get("row_count"),
            status="completed",
            conversation_id=conv_id,
            task_id=ctx.task_id,
        )

        # Persist context summary
        summary = cm.get_summary()
        if summary:
            self.store.update_conversation_summary(conv_id, summary)

        ctx.status = TaskStatus.COMPLETED
        return self._build_response(ctx)

    def _build_response(
        self,
        ctx: TaskContext,
        status: Optional[str] = None,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        resp: Dict[str, Any] = {
            "status": status or ctx.status.value,
            "task_id": ctx.task_id,
            "intent": ctx.intent.value if ctx.intent else None,
            "generated_sql": ctx.generated_sql,
            "explanation": ctx.explanation,
            "agent_trace": [
                {"role": m.role, "content": m.content, "agent": m.agent}
                for m in ctx.messages
            ],
        }
        if ctx.execution_result:
            resp["results"] = ctx.execution_result.get("results", [])
            resp["row_count"] = ctx.execution_result.get("row_count", 0)
        if ctx.needs_confirmation:
            resp["confirmation_message"] = ctx.confirmation_message
            resp["validation"] = ctx.validation_result
        if extra_data:
            resp.update(extra_data)
        return resp

    def _error_response(self, ctx: TaskContext, error: str) -> Dict[str, Any]:
        ctx.status = TaskStatus.FAILED
        ctx.error = error
        return self._build_response(ctx, status="error") | {"error": error}
