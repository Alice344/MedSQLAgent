"""Database schema initialization for the SQLite-backed context store."""

from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger(__name__)


def init_context_store_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id            TEXT PRIMARY KEY,
            connection_id TEXT NOT NULL,
            created_at    REAL NOT NULL,
            updated_at    REAL NOT NULL,
            summary       TEXT DEFAULT '',
            metadata      TEXT DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_conv_conn
            ON conversations(connection_id);

        CREATE TABLE IF NOT EXISTS messages (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            role            TEXT NOT NULL,
            content         TEXT NOT NULL,
            agent           TEXT,
            timestamp       REAL NOT NULL,
            metadata        TEXT DEFAULT '{}',
            FOREIGN KEY (conversation_id) REFERENCES conversations(id)
        );

        CREATE INDEX IF NOT EXISTS idx_msg_conv
            ON messages(conversation_id);

        CREATE TABLE IF NOT EXISTS query_history (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            connection_id   TEXT NOT NULL,
            conversation_id TEXT,
            task_id         TEXT,
            user_query      TEXT NOT NULL,
            generated_sql   TEXT,
            row_count       INTEGER,
            status          TEXT NOT NULL DEFAULT 'completed',
            error           TEXT,
            created_at      REAL NOT NULL,
            metadata        TEXT DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_qh_conn
            ON query_history(connection_id);

        CREATE TABLE IF NOT EXISTS query_attempts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            connection_id   TEXT NOT NULL,
            conversation_id TEXT,
            task_id         TEXT NOT NULL,
            user_query      TEXT NOT NULL,
            generated_sql   TEXT,
            status          TEXT NOT NULL DEFAULT 'generated',
            error           TEXT,
            created_at      REAL NOT NULL,
            updated_at      REAL NOT NULL,
            metadata        TEXT DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_query_attempts_task
            ON query_attempts(task_id);

        CREATE TABLE IF NOT EXISTS query_corrections (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            connection_id   TEXT NOT NULL,
            conversation_id TEXT,
            task_id         TEXT,
            user_query      TEXT NOT NULL,
            original_sql    TEXT NOT NULL,
            corrected_sql   TEXT NOT NULL,
            correction_kind TEXT NOT NULL DEFAULT 'manual_edit',
            created_at      REAL NOT NULL,
            metadata        TEXT DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_query_corrections_task
            ON query_corrections(task_id);

        CREATE TABLE IF NOT EXISTS skill_candidates (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            connection_id      TEXT NOT NULL,
            candidate_key      TEXT NOT NULL UNIQUE,
            title              TEXT NOT NULL,
            summary            TEXT NOT NULL,
            trigger_query      TEXT NOT NULL,
            representative_sql TEXT,
            confidence         REAL NOT NULL DEFAULT 0,
            status             TEXT NOT NULL DEFAULT 'pending',
            created_at         REAL NOT NULL,
            updated_at         REAL NOT NULL,
            metadata           TEXT DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_skill_candidates_conn
            ON skill_candidates(connection_id, status);

        CREATE TABLE IF NOT EXISTS published_skills (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            connection_id      TEXT NOT NULL,
            skill_candidate_id INTEGER,
            title              TEXT NOT NULL,
            summary            TEXT NOT NULL,
            instructions       TEXT NOT NULL,
            status             TEXT NOT NULL DEFAULT 'active',
            created_at         REAL NOT NULL,
            updated_at         REAL NOT NULL,
            metadata           TEXT DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_published_skills_conn
            ON published_skills(connection_id, status);

        CREATE TABLE IF NOT EXISTS skill_usage_history (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            connection_id      TEXT NOT NULL,
            task_id            TEXT,
            published_skill_id INTEGER NOT NULL,
            user_query         TEXT NOT NULL,
            match_score        REAL,
            outcome            TEXT NOT NULL DEFAULT 'used',
            created_at         REAL NOT NULL,
            metadata           TEXT DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_skill_usage_skill
            ON skill_usage_history(published_skill_id);

        CREATE TABLE IF NOT EXISTS task_state (
            task_id         TEXT PRIMARY KEY,
            connection_id   TEXT NOT NULL,
            conversation_id TEXT,
            status          TEXT NOT NULL,
            payload         TEXT NOT NULL,
            updated_at      REAL NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_task_state_conn
            ON task_state(connection_id);
        """
    )
    logger.info("Context store schema initialized")
