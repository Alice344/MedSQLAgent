"""
Streamlit frontend for SQL Agent — Multi-Agent Edition.

Supports:
- Conversational chat interface with the agent pipeline
- Human-in-the-loop: review & confirm/reject/modify generated SQL
- Conversation history across turns
- Query history sidebar
- Legacy raw-SQL tab (unchanged)
"""
import os

import streamlit as st
import requests
import json
import pandas as pd

# ── Configuration ────────────────────────────────────────────────────────────

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8001")

st.set_page_config(
    page_title="SQL Agent — Multi-Agent",
    page_icon="🤖",
    layout="wide",
)

# ── Session state defaults ───────────────────────────────────────────────────

_DEFAULTS = {
    "connection_id": None,
    "last_sql_query": None,
    "chat_messages": [],       # [{role, content, data?, ...}]
    "pending_task": None,      # task awaiting confirmation
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ── API helpers ──────────────────────────────────────────────────────────────


def _api_post(path: str, payload: dict, timeout: int = 60):
    try:
        r = requests.post(f"{API_BASE_URL}{path}", json=payload, timeout=timeout)
        if r.status_code == 200:
            return True, r.json(), None
        ct = r.headers.get("content-type", "")
        err = r.json().get("detail", r.text) if "json" in ct else r.text
        return False, None, err
    except requests.RequestException as e:
        return False, None, str(e)


def _api_get(path: str, params=None, timeout: int = 15):
    try:
        r = requests.get(f"{API_BASE_URL}{path}", params=params, timeout=timeout)
        if r.status_code == 200:
            return True, r.json(), None
        ct = r.headers.get("content-type", "")
        err = r.json().get("detail", r.text) if "json" in ct else r.text
        return False, None, err
    except requests.RequestException as e:
        return False, None, str(e)


def _api_delete(path: str, timeout: int = 15):
    try:
        r = requests.delete(f"{API_BASE_URL}{path}", timeout=timeout)
        return r.status_code == 200
    except requests.RequestException:
        return False


def connect_to_database(server, database, username, password, port, use_mfa,
                        refresh_schema=False, use_wholegraph=False):
    return _api_post("/api/connect", {
        "server": server,
        "database": database,
        "username": username,
        "password": password if password else None,
        "port": port,
        "auth_method": "azure_ad" if use_mfa else "sql",
        "use_mfa": use_mfa,
        "refresh_schema": refresh_schema,
        "use_wholegraph": use_wholegraph,
    }, timeout=120)


def agent_chat(message: str, connection_id: str):
    return _api_post("/api/agent/chat", {
        "message": message,
        "connection_id": connection_id,
    })


def agent_confirm(task_id: str, connection_id: str, modified_sql=None):
    payload = {"task_id": task_id, "connection_id": connection_id}
    if modified_sql:
        payload["modified_sql"] = modified_sql
    return _api_post("/api/agent/confirm", payload)


def agent_reject(task_id: str, connection_id: str, reason: str = ""):
    return _api_post("/api/agent/reject", {
        "task_id": task_id,
        "connection_id": connection_id,
        "reason": reason,
    })


def execute_raw_sql(sql_query, connection_id):
    return _api_post(f"/api/query/execute-sql/{connection_id}", {"sql_query": sql_query})


def refresh_schema_from_db(connection_id):
    return _api_post(f"/api/schema/{connection_id}/refresh", {}, timeout=300)


# ── UI helpers ───────────────────────────────────────────────────────────────


def _render_chat_message(msg):
    """Render one chat message in the Streamlit chat container."""
    role = msg["role"]
    content = msg["content"]

    if role == "user":
        with st.chat_message("user"):
            st.markdown(content)
    elif role == "assistant":
        with st.chat_message("assistant"):
            st.markdown(content)
    elif role == "sql":
        with st.chat_message("assistant"):
            st.code(content, language="sql")
    elif role == "results":
        with st.chat_message("assistant"):
            data = msg.get("data", {})
            results = data.get("results", [])
            row_count = data.get("row_count", 0)
            if results:
                st.markdown(f"**Results** ({row_count} rows)")
                df = pd.DataFrame(results)
                st.dataframe(df, use_container_width=True)
                col1, col2 = st.columns(2)
                with col1:
                    st.download_button("📥 CSV", df.to_csv(index=False),
                                       "results.csv", "text/csv",
                                       use_container_width=True)
                with col2:
                    st.download_button("📥 JSON", json.dumps(results, indent=2),
                                       "results.json", "application/json",
                                       use_container_width=True)
            else:
                st.info("Query executed successfully — no rows returned.")
    elif role == "agent_trace":
        with st.chat_message("assistant"):
            with st.expander("🔍 Agent reasoning trace", expanded=False):
                for step in msg.get("trace", []):
                    agent_name = step.get("agent", "unknown")
                    st.markdown(f"**[{agent_name}]** {step['content']}")
    elif role == "error":
        with st.chat_message("assistant"):
            st.error(f"❌ {content}")


def _add_chat(role, content, **kwargs):
    """Append a message to session chat history."""
    st.session_state.chat_messages.append({"role": role, "content": content, **kwargs})


# ── Health check ─────────────────────────────────────────────────────────────

try:
    health = requests.get(f"{API_BASE_URL}/api/health", timeout=5)
    if health.status_code != 200:
        st.error("⚠️ Backend not responding. Start it with `python run.py` in the backend folder.")
        st.stop()
except Exception:
    st.error(f"⚠️ Cannot connect to backend at {API_BASE_URL}")
    st.stop()

# ── Login section ────────────────────────────────────────────────────────────

if st.session_state.connection_id is None:
    st.title("🤖 SQL Agent — Multi-Agent")
    st.markdown("Connect to your Microsoft SQL Server database and query using natural language")

    st.header("Database Connection")
    with st.form("connection_form"):
        col1, col2 = st.columns(2)
        with col1:
            server = st.text_input("Server", placeholder="your-server.database.windows.net")
            database = st.text_input("Database", placeholder="Caboodle")
            username = st.text_input("Username", placeholder="user@domain.com")
        with col2:
            password = st.text_input("Password (optional for MFA)", type="password")
            port = st.number_input("Port", value=1433, min_value=1, max_value=65535)
            use_mfa = st.checkbox("Azure AD MFA", value=True)
            refresh_schema = st.checkbox("Re-fetch schema on connect", value=False)
            use_wholegraph = st.checkbox("Use Wholegraph schema", value=True)

        if st.form_submit_button("Connect", use_container_width=True):
            if not all([server, database, username]):
                st.error("Please fill in Server, Database, and Username")
            else:
                with st.spinner("Connecting… (MFA may open a browser window)"):
                    ok, data, err = connect_to_database(
                        server, database, username, password, port, use_mfa,
                        refresh_schema, use_wholegraph
                    )
                if ok:
                    st.session_state.connection_id = data["connection_id"]
                    source = data.get("schema_source", "database")
                    st.success(
                        f"✅ Connected — {data['tables_count']} tables, "
                        f"{data['foreign_keys_count']} FKs ({source})"
                    )
                    st.rerun()
                else:
                    st.error(f"❌ {err}")

# ── Main app (connected) ────────────────────────────────────────────────────

else:
    conn_id = st.session_state.connection_id

    # Sidebar
    with st.sidebar:
        st.markdown(f"**Connected** `{conn_id[:8]}…`")

        if st.button("🔄 Refresh schema"):
            with st.spinner("Refreshing…"):
                ok, p, err = refresh_schema_from_db(conn_id)
                if ok:
                    st.success(f"Schema: {p['tables_count']} tables")
                else:
                    st.error(err)

        if st.button("🗑️ Clear chat"):
            st.session_state.chat_messages = []
            st.session_state.pending_task = None
            _api_delete(f"/api/agent/history/{conn_id}")
            st.rerun()

        if st.button("➕ New conversation"):
            st.session_state.chat_messages = []
            st.session_state.pending_task = None
            _api_post(f"/api/agent/new-conversation/{conn_id}", {})
            st.rerun()

        if st.button("🚪 Disconnect"):
            st.session_state.connection_id = None
            st.session_state.chat_messages = []
            st.session_state.pending_task = None
            st.session_state.last_sql_query = None
            st.rerun()

        # Query history
        st.markdown("---")
        st.markdown("### Recent queries")
        ok, qh, _ = _api_get(f"/api/agent/query-history/{conn_id}", {"limit": 10})
        if ok and qh:
            for q in qh:
                status_icon = "✅" if q["status"] == "completed" else "❌"
                label = q["user_query"][:60] + ("…" if len(q["user_query"]) > 60 else "")
                st.caption(f"{status_icon} {label}")

    # Main area
    st.title("🤖 SQL Agent")

    tab_chat, tab_sql = st.tabs(["💬 Chat", "📝 Raw SQL"])

    # ── Chat tab ─────────────────────────────────────────────────────────

    with tab_chat:
        # Render existing messages
        for msg in st.session_state.chat_messages:
            _render_chat_message(msg)

        # Pending confirmation UI
        if st.session_state.pending_task:
            task = st.session_state.pending_task
            with st.chat_message("assistant"):
                st.warning("⚠️ SQL requires your confirmation before execution")
                st.code(task["generated_sql"], language="sql")
                if task.get("confirmation_message"):
                    st.markdown(task["confirmation_message"])

                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.button("✅ Execute", type="primary", use_container_width=True):
                        with st.spinner("Executing…"):
                            ok, data, err = agent_confirm(task["task_id"], conn_id)
                        st.session_state.pending_task = None
                        if ok and data.get("status") == "completed":
                            _add_chat("sql", data.get("generated_sql", ""))
                            if data.get("explanation"):
                                _add_chat("assistant", data["explanation"])
                            if data.get("results"):
                                _add_chat("results", "", data={
                                    "results": data["results"],
                                    "row_count": data.get("row_count", 0),
                                })
                            if data.get("agent_trace"):
                                _add_chat("agent_trace", "", trace=data["agent_trace"])
                        elif ok:
                            _add_chat("assistant", f"Status: {data.get('status', 'unknown')}")
                        else:
                            _add_chat("error", err or "Execution failed")
                        st.rerun()

                with col2:
                    if st.button("❌ Cancel", use_container_width=True):
                        agent_reject(task["task_id"], conn_id, "User cancelled")
                        st.session_state.pending_task = None
                        _add_chat("assistant", "Query cancelled.")
                        st.rerun()

                with col3:
                    if st.button("✏️ Modify SQL", use_container_width=True):
                        st.session_state["_editing_sql"] = task["generated_sql"]

                # Editable SQL area (shown when user clicks Modify)
                if st.session_state.get("_editing_sql"):
                    modified = st.text_area("Edit SQL:", value=st.session_state["_editing_sql"],
                                            height=150)
                    if st.button("Submit modified SQL", type="primary"):
                        with st.spinner("Executing modified SQL…"):
                            ok, data, err = agent_confirm(task["task_id"], conn_id,
                                                          modified_sql=modified)
                        st.session_state.pending_task = None
                        st.session_state.pop("_editing_sql", None)
                        if ok and data.get("status") == "completed":
                            _add_chat("sql", data.get("generated_sql", modified))
                            if data.get("explanation"):
                                _add_chat("assistant", data["explanation"])
                            if data.get("results"):
                                _add_chat("results", "", data={
                                    "results": data["results"],
                                    "row_count": data.get("row_count", 0),
                                })
                        else:
                            _add_chat("error", err or "Execution failed")
                        st.rerun()

        # Chat input
        with st.form("chat_prompt_form", clear_on_submit=True):
            input_col, button_col = st.columns([6, 1])
            with input_col:
                user_input = st.text_input(
                    "Ask a question about your database",
                    placeholder="Ask a question about your database…",
                    label_visibility="collapsed",
                )
            with button_col:
                send_clicked = st.form_submit_button("Send", use_container_width=True)

        if send_clicked and user_input.strip():
            user_input = user_input.strip()
            _add_chat("user", user_input)
            with st.chat_message("user"):
                st.markdown(user_input)

            with st.chat_message("assistant"):
                with st.spinner("🤖 Agents working…"):
                    ok, data, err = agent_chat(user_input, conn_id)

            if not ok:
                _add_chat("error", err or "Agent pipeline failed")
                st.rerun()
            else:
                status = data.get("status", "")

                # Show agent trace
                if data.get("agent_trace"):
                    _add_chat("agent_trace", "", trace=data["agent_trace"])

                if status == "awaiting_confirmation":
                    st.session_state.pending_task = data
                    _add_chat("assistant",
                              "I've generated SQL for your request. Please review before execution.")
                    st.rerun()

                elif status == "completed":
                    if data.get("generated_sql"):
                        _add_chat("sql", data["generated_sql"])
                        st.session_state.last_sql_query = data["generated_sql"]
                    if data.get("explanation"):
                        _add_chat("assistant", data["explanation"])
                    if data.get("results") is not None:
                        _add_chat("results", "", data={
                            "results": data.get("results", []),
                            "row_count": data.get("row_count", 0),
                        })
                    st.rerun()

                elif status == "clarification_needed":
                    refined = data.get("refined_query", "Could you clarify your request?")
                    _add_chat("assistant", refined)
                    st.rerun()

                elif status == "error":
                    _add_chat("error", data.get("error", "Unknown error"))
                    st.rerun()

                else:
                    # Schema explore or other
                    if data.get("tables"):
                        tables_info = data["tables"]
                        lines = [f"Found **{data.get('total_tables', len(tables_info))}** tables:\n"]
                        for t in tables_info[:30]:
                            desc = f" — {t['description']}" if t.get("description") else ""
                            lines.append(f"- `{t['full_name']}` ({t['column_count']} cols){desc}")
                        if len(tables_info) > 30:
                            lines.append(f"- … and {len(tables_info) - 30} more")
                        _add_chat("assistant", "\n".join(lines))
                    if data.get("explanation"):
                        _add_chat("assistant", data["explanation"])
                    st.rerun()

        elif send_clicked:
            st.warning("Enter a question first")

    # ── Raw SQL tab ──────────────────────────────────────────────────────

    with tab_sql:
        st.markdown("### Execute SQL directly")
        sql_query = st.text_area(
            "SQL query",
            value=st.session_state.last_sql_query or "",
            placeholder="SELECT TOP 100 * FROM dbo.PatientDim;",
            height=150,
        )
        if st.button("Execute SQL", type="primary", use_container_width=True):
            if sql_query:
                with st.spinner("Executing…"):
                    ok, data, err = execute_raw_sql(sql_query, conn_id)
                if ok:
                    st.session_state.last_sql_query = sql_query
                    results = data.get("results", [])
                    if results:
                        st.markdown(f"### Results ({data.get('row_count', len(results))} rows)")
                        df = pd.DataFrame(results)
                        st.dataframe(df, use_container_width=True)
                        c1, c2 = st.columns(2)
                        with c1:
                            st.download_button("CSV", df.to_csv(index=False),
                                               "results.csv", "text/csv",
                                               use_container_width=True)
                        with c2:
                            st.download_button("JSON", json.dumps(results, indent=2),
                                               "results.json", "application/json",
                                               use_container_width=True)
                    else:
                        st.success("Executed successfully — no rows returned.")
                else:
                    st.error(f"❌ {err}")
            else:
                st.warning("Enter a SQL query first")
