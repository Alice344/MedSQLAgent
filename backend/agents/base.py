"""
Base classes shared by every agent.

Provides:
- Enum types for roles, statuses, intents
- AgentMessage / TaskContext data classes
- AgentResult – standardised output
- BaseAgent   – abstract base with OpenAI helper
"""
from __future__ import annotations

import logging
import os
import re
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────────


class AgentRole(str, Enum):
    ORCHESTRATOR = "orchestrator"
    INTENT = "intent"
    SCHEMA = "schema"
    SQL_GENERATOR = "sql_generator"
    VALIDATOR = "validator"
    EXECUTOR = "executor"
    EXPLAINER = "explainer"
    VISUALIZER = "visualizer"


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    COMPLETED = "completed"
    FAILED = "failed"


class IntentType(str, Enum):
    QUERY = "query"
    SCHEMA_EXPLORE = "schema_explore"
    EXPORT = "export"
    MODIFY = "modify"
    EXPLAIN = "explain"
    FOLLOWUP = "followup"
    CLARIFY = "clarify"
    GENERAL = "general"
    VISUALIZE = "visualize"


# ── Data classes ─────────────────────────────────────────────────────────────


@dataclass
class AgentMessage:
    """A single message exchanged in the agent pipeline."""

    role: str  # "user" | "assistant" | "system" | "agent"
    content: str
    agent: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    token_count: int = 0


@dataclass
class TaskContext:
    """Mutable context that flows through the agent pipeline for one user turn."""

    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    connection_id: str = ""
    user_query: str = ""
    refined_query: str = ""  # After intent agent clarification

    # Pipeline artefacts
    intent: Optional[IntentType] = None
    selected_tables: List[str] = field(default_factory=list)
    relevant_schema: Optional[Dict[str, Any]] = None
    formatted_schema: str = ""
    generated_sql: Optional[str] = None
    validation_result: Optional[Dict[str, Any]] = None
    execution_result: Optional[Dict[str, Any]] = None
    explanation: Optional[str] = None
    visualization_config: Optional[Dict[str, Any]] = None
    matched_skills: List[Dict[str, Any]] = field(default_factory=list)

    # Status
    status: TaskStatus = TaskStatus.PENDING
    error: Optional[str] = None
    needs_confirmation: bool = False
    confirmation_message: Optional[str] = None

    # Agent trace – messages produced during this task
    messages: List[AgentMessage] = field(default_factory=list)

    # Timestamps
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def add_message(
        self, role: str, content: str, agent: Optional[str] = None, **meta: Any
    ) -> None:
        self.messages.append(
            AgentMessage(role=role, content=content, agent=agent, metadata=meta)
        )
        self.updated_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a JSON-safe dict for API responses."""
        return {
            "task_id": self.task_id,
            "connection_id": self.connection_id,
            "user_query": self.user_query,
            "refined_query": self.refined_query,
            "intent": self.intent.value if self.intent else None,
            "selected_tables": self.selected_tables,
            "generated_sql": self.generated_sql,
            "validation_result": self.validation_result,
            "execution_result": self.execution_result,
            "explanation": self.explanation,
            "matched_skills": self.matched_skills,
            "status": self.status.value,
            "error": self.error,
            "needs_confirmation": self.needs_confirmation,
            "confirmation_message": self.confirmation_message,
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "agent": m.agent,
                    "timestamp": m.timestamp,
                }
                for m in self.messages
            ],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# ── Result ───────────────────────────────────────────────────────────────────


@dataclass
class AgentResult:
    """Standardised result returned by every agent."""

    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    needs_confirmation: bool = False
    confirmation_message: Optional[str] = None
    next_agent: Optional[AgentRole] = None


# ── Base Agent ───────────────────────────────────────────────────────────────


class BaseAgent(ABC):
    """Abstract base class for all agents."""

    role: AgentRole = AgentRole.ORCHESTRATOR
    default_model: str = "gpt-4o-mini"

    def __init__(self, model: Optional[str] = None):
        from llm.client import get_llm_client, get_model_name

        self.model = model or get_model_name()
        self.client = get_llm_client()
        self.logger = logging.getLogger(f"agent.{self.role.value}")

    # ── LLM helper ───────────────────────────────────────────────────────

    def _chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 1000,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Call OpenAI chat completion; returns the text content."""
        kwargs: Dict[str, Any] = dict(
            model=model or self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if response_format:
            kwargs["response_format"] = response_format
        try:
            resp = self.client.chat.completions.create(**kwargs)
        except Exception as exc:
            err_msg = str(exc).lower()
            if "context_length" in err_msg or "token" in err_msg or "too long" in err_msg:
                self.logger.error("LLM context length exceeded: %s", exc)
                raise RuntimeError(
                    "The conversation is too long for the model's context window. "
                    "Please start a new conversation."
                ) from exc
            if "timeout" in err_msg or "timed out" in err_msg:
                self.logger.error("LLM request timed out: %s", exc)
                raise RuntimeError(
                    "The LLM request timed out. Please try again."
                ) from exc
            self.logger.error("LLM API error: %s", exc)
            raise RuntimeError(f"LLM call failed: {exc}") from exc
        raw = (resp.choices[0].message.content or "").strip()
        # Strip DeepSeek-R1 reasoning blocks
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        return raw

    # ── Abstract ─────────────────────────────────────────────────────────

    @abstractmethod
    def run(self, ctx: TaskContext, **kwargs: Any) -> AgentResult:
        """Execute this agent's work.  Must be implemented by subclasses."""
        ...
