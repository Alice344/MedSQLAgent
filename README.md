# MedSQLAgent

MedSQLAgent is a human-in-the-loop SQL agent for complex healthcare analytics workflows. It turns natural language questions into SQL, pauses for human review before execution, learns from successful examples, and promotes repeated business patterns into reviewable skill candidates.

The goal is not just "generate SQL." The goal is to build an agent that can steadily absorb domain knowledge without losing safety.

## What It Does

- Connects to SQL Server and Azure AD / MFA-backed databases
- Retrieves relevant schema from markdown table docs plus the schema graph
- Pulls similar historical `natural language -> SQL` examples from memory
- Generates SQL with mandatory human confirmation before execution
- Writes successful `NL + SQL` pairs back into memory
- Detects repeated successful patterns and drafts skill candidates
- Requires manual approval before any skill becomes a published runtime skill
- Updates per-table markdown docs after successful executed queries

## Product Shape

The interface is organized around three workflows:

- `Chat`
  - Ask natural-language database questions
  - Review generated SQL
  - Confirm, edit, or reject before execution
- `Raw SQL`
  - Run SQL directly when you already know exactly what you want
- `Learning`
  - Review auto-detected skill candidates
  - Edit title and instructions
  - Approve or reject before they influence future SQL generation

## Core Ideas

### 1. Human-In-The-Loop First

Generated SQL is not executed blindly. The backend always pauses in an `awaiting_confirmation` state so the user can:

- execute as-is
- modify the SQL and then execute
- reject the query

### 2. Memory Before Skills

The system first learns from concrete examples:

- successful executed SQL
- modified SQL before execution
- repeated table usage
- repeated join / filter patterns

This memory layer is what later feeds skill creation.

### 3. Skills Need Manual Approval

The agent can suggest a reusable skill when it sees enough repeated successful patterns, but it cannot publish that skill on its own.

Every skill candidate must be reviewed by a human before it becomes a published runtime skill.

## Learning Pipeline

```text
User question
  -> markdown + schema retrieval
  -> similar history retrieval
  -> published skill matching
  -> SQL generation
  -> human SQL review
  -> execution
  -> explanation + result display
  -> write successful NL+SQL back to memory
  -> detect repeated patterns
  -> create skill candidate
  -> manual skill approval
  -> published skill reused on future similar questions
```

## Repository Structure

```text
backend/
  agents/          multi-agent workflow and HITL orchestration
  context/         SQLite-backed memory store
  database/        DB connection, schema extraction, wholegraph loading
  learning/        repeated-pattern detection
  llm/             schema retrieval and SQL prompting
  skills/          published skill policy + runtime routing
  table_docs/      markdown schema docs and auto-update logic

frontend/
  app/             Next.js pages
  components/      chat, SQL review, learning panel, results, charts
  lib/             frontend API client and shared types
  store/           Zustand app state
```

## Local Setup

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env`:

```bash
OPENAI_API_KEY=your_key_here
```

Run the backend:

```bash
python run_port_8001.py
```

Backend default URL:

```text
http://localhost:8001
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend default URL:

```text
http://localhost:3000
```

## Data and Privacy Notes

These local assets are intentionally git-ignored and should not be published:

- `backend/data/conversations.db`
- `backend/wholegraph.json`
- `docs/caboodle/`

They may contain schema details, local learning history, or internal documentation.

## Current Learning Objects

The app now tracks multiple kinds of learning state:

- `query_history`
  - successful executed `NL + SQL` pairs
- `query_attempts`
  - generated SQL drafts and execution lifecycle
- `query_corrections`
  - user-edited SQL before execution
- `skill_candidates`
  - auto-detected reusable patterns awaiting review
- `published_skills`
  - manually approved reusable business skills
- `skill_usage_history`
  - when and how published skills were used

## Runtime Retrieval Order

When the user asks a question, the backend now combines four sources of context:

1. markdown table docs
2. FK-neighbor schema expansion
3. similar successful historical examples
4. published, manually approved skills

Published skills are treated as stronger guidance than generic few-shot examples.

## API Highlights

### Main Agent Flow

- `POST /api/agent/chat`
- `POST /api/agent/confirm`
- `POST /api/agent/reject`
- `POST /api/agent/visualize`

### History and Learning

- `GET /api/agent/query-history/{connection_id}`
- `GET /api/agent/skill-candidates/{connection_id}`
- `GET /api/agent/published-skills/{connection_id}`
- `POST /api/agent/skill-candidates/approve`
- `POST /api/agent/skill-candidates/reject`

## What Is Still Deliberately Manual

- final SQL approval
- skill publication
- high-risk business-rule acceptance

That boundary is intentional. The system is meant to learn aggressively, but publish conservatively.
