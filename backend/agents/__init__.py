"""
Multi-agent framework for MedSQLAgent.

Agents
------
- IntentAgent      – classifies user intent
- SchemaAgent      – selects relevant tables via RAG
- SQLGeneratorAgent – generates T-SQL from natural language
- ValidationAgent  – reviews SQL for safety / correctness
- ExecutionAgent   – executes confirmed SQL
- ExplanationAgent – explains queries and results in plain language
- Orchestrator     – routes tasks through the pipeline with human-in-the-loop
"""

from .base import (
    AgentRole,
    TaskStatus,
    IntentType,
    AgentMessage,
    TaskContext,
    AgentResult,
    BaseAgent,
)
from .orchestrator import Orchestrator

__all__ = [
    "AgentRole",
    "TaskStatus",
    "IntentType",
    "AgentMessage",
    "TaskContext",
    "AgentResult",
    "BaseAgent",
    "Orchestrator",
]
