"""
FastAPI backend for SQL Agent
"""
from pathlib import Path

from dotenv import load_dotenv

# Load backend/.env so OPENAI_API_KEY is available to the LLM (see .env.example)
load_dotenv(Path(__file__).resolve().parent / ".env")

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, Response
from pydantic import BaseModel, field_validator
from typing import Optional, Dict, Any, List
import hashlib
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
import json
import io
import csv
import logging

from database.connection import DatabaseConnection
from database.schema_extractor import SchemaExtractor
from database.schema_storage import SchemaStorage
from database.wholegraph_loader import load_wholegraph_schema
from llm.sql_generator import SQLGenerator
from llm.schema_retriever import retrieve_relevant_schema
from table_docs.table_doc_updater import update_table_docs_for_query

# Multi-agent system
from agents.orchestrator import Orchestrator
from context.store import ConversationStore

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="SQL Agent API")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Browsers request this automatically; avoid noisy 404s in logs."""
    return Response(status_code=204)


@app.get("/health")
async def health_check():
    """Health check endpoint for Azure App Service / load balancers."""
    return {"status": "healthy", "active_connections": len(active_connections)}


# CORS middleware – configurable via ALLOWED_ORIGINS env var.
# Default "*" for local dev; set to your frontend URL in production.
import os as _os
_allowed_origins = [
    o.strip()
    for o in _os.getenv("ALLOWED_ORIGINS", "*").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# ── Connection cap ───────────────────────────────────────────────────────────
MAX_ACTIVE_CONNECTIONS = int(_os.getenv("MAX_CONNECTIONS", "100"))

# Initialize storage
schema_storage = SchemaStorage()

# Store active connections (in production, use Redis or similar)
active_connections: Dict[str, DatabaseConnection] = {}

# Multi-agent orchestrator (lazy – created after schema_storage is ready)
conversation_store = ConversationStore()
orchestrator = Orchestrator(
    schema_storage=schema_storage,
    conversation_store=conversation_store,
)


# Pydantic models
class DatabaseCredentials(BaseModel):
    server: str
    database: str
    username: str
    password: Optional[str] = None
    port: int = 1433
    auth_method: str = "sql"  # 'sql' or 'azure_ad'
    use_mfa: bool = False  # Use ActiveDirectoryInteractive for MFA
    refresh_schema: bool = False
    use_wholegraph: bool = False

    @field_validator("server", "database", "username", mode="before")
    @classmethod
    def strip_whitespace(cls, v):
        return v.strip() if isinstance(v, str) else v


class QueryRequest(BaseModel):
    natural_language_query: str
    connection_id: str


class QueryResponse(BaseModel):
    sql_query: str
    results: list
    row_count: int
    explanation: Optional[str] = None


def sanitize_query_rows(rows: Any) -> List[Dict[str, Any]]:
    """Make pyodbc rows JSON-safe (Decimal, datetime, bytes, UUID, etc.)."""
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


def get_connection_id(credentials: DatabaseCredentials) -> str:
    """Generate unique connection ID from credentials"""
    key = f"{credentials.server}:{credentials.port}:{credentials.database}:{credentials.username}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


# In-memory only: lost on uvicorn --reload or process restart. Client must POST /api/connect again.
SESSION_EXPIRED_DETAIL = (
    "No active database session. The API was restarted or reloaded, which clears open "
    "connections. Return to the login page and click Connect again — same server/user/database "
    "reuses your cached schema file."
)


def require_db_connection(connection_id: str) -> DatabaseConnection:
    """Return the live ODBC connection or fail with 503 (session expired)."""
    conn = active_connections.get(connection_id)
    if not conn:
        raise HTTPException(status_code=503, detail=SESSION_EXPIRED_DETAIL)
    return conn


@app.post("/api/connect")
async def connect_database(credentials: DatabaseCredentials):
    """Connect to database; schema is loaded from cache unless missing or refresh_schema is True."""
    try:
        # Create connection
        db_conn = DatabaseConnection(
            server=credentials.server,
            database=credentials.database,
            username=credentials.username,
            password=credentials.password,
            port=credentials.port,
            auth_method=credentials.auth_method,
            use_mfa=credentials.use_mfa
        )
        
        # Test connection
        try:
            if not db_conn.test_connection():
                raise HTTPException(
                    status_code=400, 
                    detail="Failed to connect to database. Please check your credentials and server settings."
                )
        except Exception as conn_error:
            error_msg = str(conn_error)
            # Provide more helpful error messages
            if "ODBC Driver" in error_msg or "driver" in error_msg.lower():
                raise HTTPException(
                    status_code=400,
                    detail="ODBC Driver 17 for SQL Server not found. Please install it from: https://docs.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server"
                )
            elif "login" in error_msg.lower() or "authentication" in error_msg.lower():
                raise HTTPException(
                    status_code=400,
                    detail="Authentication failed. Please check your username and password."
                )
            elif "server" in error_msg.lower() or "network" in error_msg.lower():
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot reach server. Error: {error_msg}"
                )
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Connection failed: {error_msg}"
                )
        
        # Generate connection ID
        connection_id = get_connection_id(credentials)

        cached_schema = schema_storage.load_schema(connection_id)
        schema_from_cache = bool(
            cached_schema and not credentials.refresh_schema and not credentials.use_wholegraph
        )

        if schema_from_cache:
            schema = cached_schema
            logger.info(
                "Using cached schema for %s (%s tables)",
                connection_id,
                len(schema.get("tables", [])),
            )
        elif credentials.use_wholegraph:
            try:
                schema = load_wholegraph_schema()
            except Exception as wg_error:
                logger.error(f"Wholegraph load error: {wg_error}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to load wholegraph.json: {str(wg_error)}",
                )

            # Filter wholegraph to only tables/columns that actually exist in the DB,
            # matching by table name (ignoring schema prefix) and remapping to
            # whatever schema the real DB uses.
            try:
                # real_name_map: bare "TableName" -> "RealSchema.TableName"
                real_name_map: Dict[str, str] = {}
                # real_columns: "RealSchema.TableName" -> set of column names
                real_columns: Dict[str, set] = {}
                with db_conn.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES"
                    )
                    for row in cursor.fetchall():
                        real_schema, real_name = row[0], row[1]
                        full = f"{real_schema}.{real_name}"
                        real_name_map[real_name] = full

                    cursor.execute(
                        "SELECT TABLE_SCHEMA + '.' + TABLE_NAME, COLUMN_NAME "
                        "FROM INFORMATION_SCHEMA.COLUMNS"
                    )
                    for row in cursor.fetchall():
                        real_columns.setdefault(row[0], set()).add(row[1])

                logger.info(
                    "INFORMATION_SCHEMA returned %d tables, %d total columns (sample: %s)",
                    len(real_name_map),
                    sum(len(v) for v in real_columns.values()),
                    list(real_name_map.values())[:5],
                )

                before = len(schema["tables"])
                kept = []
                for tbl in schema["tables"]:
                    bare_name = tbl["name"]  # e.g. "PatientDim"
                    if bare_name in real_name_map:
                        # Remap to real schema prefix
                        real_full = real_name_map[bare_name]
                        real_schema_part = real_full.split(".", 1)[0]
                        tbl["full_name"] = real_full
                        tbl["schema"] = real_schema_part
                        # Filter columns to only those that exist in the real table
                        db_cols = real_columns.get(real_full, set())
                        if db_cols:
                            tbl["columns"] = [
                                c for c in tbl["columns"] if c["name"] in db_cols
                            ]
                        kept.append(tbl)
                schema["tables"] = kept

                # Remap FK edges too
                wg_to_real = {t["name"]: t["full_name"] for t in kept}
                existing_full = {t["full_name"] for t in kept}
                remapped_fks = []
                for fk in schema["foreign_keys"]:
                    ft = fk["from_table"]
                    tt = fk["to_table"]
                    # Try remapping by bare name
                    ft_bare = ft.split(".", 1)[-1] if "." in ft else ft
                    tt_bare = tt.split(".", 1)[-1] if "." in tt else tt
                    ft_real = wg_to_real.get(ft_bare, ft)
                    tt_real = wg_to_real.get(tt_bare, tt)
                    if ft_real in existing_full and tt_real in existing_full:
                        remapped_fks.append({
                            **fk,
                            "from_table": ft_real,
                            "to_table": tt_real,
                        })
                schema["foreign_keys"] = remapped_fks

                logger.info(
                    "Filtered wholegraph to %d/%d tables that exist in DB (%d FKs)",
                    len(schema["tables"]), before, len(schema["foreign_keys"]),
                )
            except Exception as filter_err:
                logger.warning("Could not filter wholegraph by real tables: %s", filter_err)

            if not schema_storage.save_schema(connection_id, schema):
                logger.warning(
                    "Failed to save wholegraph schema for %s, but continuing...", connection_id
                )
        else:
            try:
                extractor = SchemaExtractor(db_conn)
                schema = extractor.extract_all_schemas()
            except Exception as schema_error:
                logger.error(f"Schema extraction error: {schema_error}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to extract schema: {str(schema_error)}",
                )

            if not schema_storage.save_schema(connection_id, schema):
                logger.warning(
                    "Failed to save schema for %s, but continuing...", connection_id
                )

        # Store connection (with cap)
        if len(active_connections) >= MAX_ACTIVE_CONNECTIONS and connection_id not in active_connections:
            # Evict the oldest connection to make room
            oldest_id = next(iter(active_connections))
            active_connections.pop(oldest_id, None)
            logger.warning("Evicted oldest connection %s (cap=%d)", oldest_id, MAX_ACTIVE_CONNECTIONS)
        active_connections[connection_id] = db_conn

        return {
            "connection_id": connection_id,
            "message": "Connected successfully",
            "tables_count": len(schema.get("tables", [])),
            "foreign_keys_count": len(schema.get("foreign_keys", [])),
            "schema_from_cache": schema_from_cache,
            "schema_source": "wholegraph" if credentials.use_wholegraph and not schema_from_cache else ("cache" if schema_from_cache else "database"),
        }
    
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Connection error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Unexpected error: {str(e)}"
        )


@app.get("/api/schema/{connection_id}")
async def get_schema(connection_id: str):
    """Get database schema"""
    schema = schema_storage.load_schema(connection_id)
    if not schema:
        raise HTTPException(status_code=404, detail="Schema not found")
    return schema


@app.get("/api/schema/{connection_id}/formatted")
async def get_formatted_schema(connection_id: str):
    """Get formatted schema for LLM"""
    schema = schema_storage.load_schema(connection_id)
    if not schema:
        raise HTTPException(status_code=404, detail="Schema not found")
    
    formatted = schema_storage.format_schema_for_llm(schema)
    return {"formatted_schema": formatted}


@app.post("/api/schema/{connection_id}/refresh")
async def refresh_schema(connection_id: str):
    """Re-extract schema from the database and overwrite the saved JSON (requires an active connection)."""
    db_conn = require_db_connection(connection_id)
    try:
        extractor = SchemaExtractor(db_conn)
        schema = extractor.extract_all_schemas()
    except Exception as e:
        logger.error(f"Schema refresh error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to refresh schema: {str(e)}")

    if not schema_storage.save_schema(connection_id, schema):
        raise HTTPException(status_code=500, detail="Failed to save refreshed schema")

    return {
        "message": "Schema refreshed from database",
        "tables_count": len(schema.get("tables", [])),
        "foreign_keys_count": len(schema.get("foreign_keys", [])),
    }


@app.post("/api/query")
async def execute_query(request: QueryRequest):
    """Execute natural language query"""
    try:
        db_conn = require_db_connection(request.connection_id)

        # Get full schema
        schema = schema_storage.load_schema(request.connection_id)
        if not schema:
            raise HTTPException(status_code=404, detail="Schema not found")

        # RAG: filter to most relevant tables so we stay within LLM token limits
        relevant_schema = retrieve_relevant_schema(
            schema,
            request.natural_language_query,
            top_k=5,
            fk_neighbor_depth=1,
        )
        logger.info(
            "RAG selected %d/%d tables for query",
            len(relevant_schema["tables"]),
            len(schema["tables"]),
        )

        # Format filtered schema for LLM
        formatted_schema = schema_storage.format_schema_for_llm(relevant_schema)

        similar_examples = conversation_store.find_similar_query_examples(
            request.natural_language_query,
            limit=3,
            connection_id=request.connection_id,
        )
        logger.info("Retrieved %d similar NL/SQL examples", len(similar_examples))

        # Generate SQL
        sql_generator = SQLGenerator()
        sql_query = sql_generator.generate_sql(
            request.natural_language_query,
            formatted_schema,
            similar_examples=similar_examples,
        )

        # Execute query
        results = db_conn.execute_query(sql_query)
        results = sanitize_query_rows(results)

        conversation_store.add_query_history(
            connection_id=request.connection_id,
            user_query=request.natural_language_query,
            generated_sql=sql_query,
            row_count=len(results) if isinstance(results, list) else 0,
            status="completed",
            metadata={
                "selected_tables": relevant_schema.get("selected_tables", []),
                "expanded_tables": relevant_schema.get("expanded_tables", []),
                "selected_chunks": relevant_schema.get("selected_chunks", []),
            },
        )

        try:
            touched_docs = update_table_docs_for_query(
                schema=schema,
                sql_query=sql_query,
                natural_language_query=request.natural_language_query,
            )
            if touched_docs:
                logger.info(
                    "Updated %d table docs after query execution: %s",
                    len(touched_docs),
                    [str(path.name) for path in touched_docs],
                )
        except Exception as doc_error:
            logger.warning("Failed to update table docs after query execution: %s", doc_error)

        # Generate explanation
        explanation = sql_generator.explain_query(sql_query)

        return QueryResponse(
            sql_query=sql_query,
            results=results,
            row_count=len(results) if isinstance(results, list) else 0,
            explanation=explanation,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Query execution failed")
        msg = str(e) or repr(e) or type(e).__name__
        raise HTTPException(status_code=500, detail=msg)


class RawSQLRequest(BaseModel):
    sql_query: str


@app.post("/api/query/execute-sql/{connection_id}")
async def execute_sql_query(connection_id: str, request: RawSQLRequest):
    """Execute raw SQL query (for testing/debugging and data manipulation)"""
    try:
        db_conn = require_db_connection(connection_id)

        results = sanitize_query_rows(db_conn.execute_query(request.sql_query))
        return {
            "results": results,
            "row_count": len(results) if isinstance(results, list) else 1,
            "message": "Query executed successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Raw SQL execution failed")
        msg = str(e) or repr(e) or type(e).__name__
        raise HTTPException(status_code=500, detail=msg)


class DownloadRequest(BaseModel):
    sql_query: str


@app.post("/api/download/{connection_id}")
async def download_results(connection_id: str, request: DownloadRequest, format: str = "csv"):
    """Download query results as CSV or JSON"""
    try:
        db_conn = require_db_connection(connection_id)

        results = sanitize_query_rows(db_conn.execute_query(request.sql_query))

        if format == "csv":
            # Convert to CSV
            output = io.StringIO()
            if results:
                writer = csv.DictWriter(output, fieldnames=results[0].keys())
                writer.writeheader()
                writer.writerows(results)
            
            return StreamingResponse(
                iter([output.getvalue()]),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename=results.csv"}
            )
        
        elif format == "json":
            return JSONResponse(
                content=results,
                headers={"Content-Disposition": f"attachment; filename=results.json"}
            )
        
        else:
            raise HTTPException(status_code=400, detail="Invalid format. Use 'csv' or 'json'")

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Download failed")
        raise HTTPException(status_code=500, detail=str(e) or repr(e))


# ═══════════════════════════════════════════════════════════════════════════
#  Multi-Agent endpoints  (new /api/agent/* routes)
# ═══════════════════════════════════════════════════════════════════════════


class AgentChatRequest(BaseModel):
    """Payload for the conversational multi-agent endpoint."""
    message: str
    connection_id: str


class AgentConfirmRequest(BaseModel):
    task_id: str
    connection_id: str
    modified_sql: Optional[str] = None


class AgentRejectRequest(BaseModel):
    task_id: str
    connection_id: str
    reason: str = ""


@app.post("/api/agent/chat")
def agent_chat(request: AgentChatRequest):
    """
    Conversational multi-agent endpoint.

    Sends the user message through the full agent pipeline:
    Intent → Schema → SQL → Validation → [HITL pause or Execute] → Explain.

    Returns a dict with ``status`` being one of:
    - ``completed``              – query executed, results included
    - ``awaiting_confirmation``  – SQL generated, needs user OK
    - ``clarification_needed``   – ambiguous request, follow-up included
    - ``error``                  – something went wrong
    """
    db_conn = active_connections.get(request.connection_id)
    if not db_conn:
        raise HTTPException(status_code=503, detail=SESSION_EXPIRED_DETAIL)

    try:
        result = orchestrator.handle_message(
            connection_id=request.connection_id,
            user_message=request.message,
            db_connection=db_conn,
        )
        return result
    except Exception as e:
        logger.exception("Agent chat failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/agent/confirm")
def agent_confirm(request: AgentConfirmRequest):
    """
    Confirm a pending task (human-in-the-loop approval).

    Optionally include ``modified_sql`` to override the generated query.
    """
    db_conn = active_connections.get(request.connection_id)
    if not db_conn:
        raise HTTPException(status_code=503, detail=SESSION_EXPIRED_DETAIL)

    try:
        result = orchestrator.confirm_task(
            task_id=request.task_id,
            db_connection=db_conn,
            modified_sql=request.modified_sql,
        )
        if result.get("status") == "error":
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Agent confirm failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/agent/reject")
def agent_reject(request: AgentRejectRequest):
    """Reject a pending task."""
    result = orchestrator.reject_task(
        task_id=request.task_id,
        reason=request.reason,
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/api/agent/history/{connection_id}")
async def agent_history(connection_id: str, limit: int = 50):
    """Get conversation history for a connection."""
    return orchestrator.get_conversation_history(connection_id, limit=limit)


class VisualizeRequest(BaseModel):
    """Request to generate visualizations from the last executed query."""
    task_id: str
    connection_id: str


@app.post("/api/agent/visualize")
def agent_visualize(request: VisualizeRequest):
    """
    Generate Plotly visualizations from results of a completed task.

    Can be called after a query has been executed to add charts.
    """
    db_conn = active_connections.get(request.connection_id)
    if not db_conn:
        raise HTTPException(status_code=503, detail=SESSION_EXPIRED_DETAIL)

    try:
        result = orchestrator.visualize_task(request.task_id)
        if result.get("status") == "error":
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Visualization failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/agent/query-history/{connection_id}")
async def agent_query_history(connection_id: str, limit: int = 20):
    """Get query history (executed SQLs) for a connection."""
    return orchestrator.get_query_history(connection_id, limit=limit)


@app.delete("/api/agent/history/{connection_id}")
async def agent_clear_history(connection_id: str):
    """Clear all conversation history for a connection."""
    orchestrator.clear_conversation(connection_id)
    return {"message": "Conversation history cleared"}


@app.post("/api/agent/new-conversation/{connection_id}")
async def agent_new_conversation(connection_id: str):
    """Start a fresh conversation thread (old messages are preserved in DB)."""
    conv_id = orchestrator.new_conversation(connection_id)
    return {"conversation_id": conv_id, "message": "New conversation started"}


# ═══════════════════════════════════════════════════════════════════════════
#  Utility endpoints
# ═══════════════════════════════════════════════════════════════════════════


@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "SQL Agent API",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/api/health",
        "endpoints": {
            "connect": "POST /api/connect",
            "schema": "GET /api/schema/{connection_id}",
            "schema_refresh": "POST /api/schema/{connection_id}/refresh",
            "query": "POST /api/query",
            "download": "POST /api/download/{connection_id}",
            "agent_chat": "POST /api/agent/chat",
            "agent_confirm": "POST /api/agent/confirm",
            "agent_reject": "POST /api/agent/reject",
            "agent_history": "GET /api/agent/history/{connection_id}",
            "agent_query_history": "GET /api/agent/query-history/{connection_id}",
            "agent_clear_history": "DELETE /api/agent/history/{connection_id}",
            "agent_new_conversation": "POST /api/agent/new-conversation/{connection_id}",
        }
    }


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
