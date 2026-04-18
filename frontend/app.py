"""
Streamlit frontend for SQL Agent
"""
import os
import streamlit as st
import requests
import json
import pandas as pd
from io import StringIO

# Configuration — override with env var for Azure deployment
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

# Page config
st.set_page_config(
    page_title="SQL Agent - Caboodle Database",
    page_icon="🔐",
    layout="wide"
)

# Initialize session state
if 'connection_id' not in st.session_state:
    st.session_state.connection_id = None
if 'last_sql_query' not in st.session_state:
    st.session_state.last_sql_query = None

def connect_to_database(server, database, username, password, port, use_mfa, refresh_schema=False, use_wholegraph=False):
    """Connect to database via API"""
    try:
        response = requests.post(
            f"{API_BASE_URL}/api/connect",
            json={
                "server": server,
                "database": database,
                "username": username,
                "password": password if password else None,
                "port": port,
                "auth_method": "azure_ad" if use_mfa else "sql",
                "use_mfa": use_mfa,
                "refresh_schema": refresh_schema,
                "use_wholegraph": use_wholegraph,
            },
            timeout=60  # Longer timeout for MFA
        )
        
        if response.status_code == 200:
            data = response.json()
            return True, data, None
        else:
            error_data = response.json()
            return False, None, error_data.get('detail', 'Connection failed')
    except requests.exceptions.RequestException as e:
        return False, None, str(e)


def refresh_schema_from_db(connection_id):
    """Re-extract schema (requires active session)."""
    try:
        r = requests.post(
            f"{API_BASE_URL}/api/schema/{connection_id}/refresh",
            timeout=300,
        )
        if r.status_code == 200:
            return True, r.json(), None
        err = r.json().get("detail", r.text) if r.headers.get("content-type", "").startswith("application/json") else r.text
        return False, None, err
    except requests.exceptions.RequestException as e:
        return False, None, str(e)


def execute_query(natural_language_query, connection_id):
    """Execute natural language query via API"""
    try:
        response = requests.post(
            f"{API_BASE_URL}/api/query",
            json={
                "natural_language_query": natural_language_query,
                "connection_id": connection_id
            },
            timeout=60
        )
        
        if response.status_code == 200:
            return True, response.json(), None
        else:
            error_data = response.json()
            return False, None, error_data.get('detail', 'Query failed')
    except requests.exceptions.RequestException as e:
        return False, None, str(e)

def execute_raw_sql(sql_query, connection_id):
    """Execute raw SQL query via API"""
    try:
        response = requests.post(
            f"{API_BASE_URL}/api/query/execute-sql/{connection_id}",
            json={"sql_query": sql_query},
            timeout=60
        )
        
        if response.status_code == 200:
            return True, response.json(), None
        else:
            error_data = response.json()
            return False, None, error_data.get('detail', 'SQL execution failed')
    except requests.exceptions.RequestException as e:
        return False, None, str(e)

# Main App
st.title("🔐 SQL Agent - Caboodle Database")
st.markdown("Connect to your Microsoft SQL Server database and query using natural language")

# Check backend connection
try:
    health_check = requests.get(f"{API_BASE_URL}/api/health", timeout=5)
    if health_check.status_code != 200:
        st.error("⚠️ Backend server is not responding. Please start it with: `python run.py` in the backend folder")
        st.stop()
except:
    st.error("⚠️ Cannot connect to backend server. Make sure it's running on http://localhost:8000")
    st.stop()

# Login Section
if st.session_state.connection_id is None:
    st.header("Database Connection")
    
    with st.form("connection_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            server = st.text_input("Server", placeholder="your-server.database.windows.net", key="server")
            database = st.text_input("Database", placeholder="Caboodle", key="database")
            username = st.text_input("Username (Azure AD Email)", placeholder="user@domain.com", key="username")
        
        with col2:
            password = st.text_input("Password (Optional for MFA)", type="password", key="password")
            port = st.number_input("Port", value=1433, min_value=1, max_value=65535, key="port")
            use_mfa = st.checkbox("Use Azure AD MFA (ActiveDirectoryInteractive)", value=True, key="use_mfa")
            refresh_schema = st.checkbox(
                "Re-fetch full schema on connect (slow); otherwise reuse saved schema",
                value=False,
                key="refresh_schema",
            )
            use_wholegraph = st.checkbox(
                "Use Wholegraph schema (Epic Caboodle — richer descriptions)",
                value=True,
                key="use_wholegraph",
            )
        
        connect_button = st.form_submit_button("Connect to Database", use_container_width=True)
        
        if connect_button:
            if not all([server, database, username]):
                st.error("Please fill in Server, Database, and Username")
            else:
                with st.spinner("Connecting to database... (If using MFA, a browser window will open)"):
                    success, data, error = connect_to_database(
                        server, database, username, password, port, use_mfa, refresh_schema, use_wholegraph
                    )

                    if success:
                        st.session_state.connection_id = data['connection_id']
                        source = data.get("schema_source", "cache" if data.get("schema_from_cache") else "database")
                        source_note = {
                            "wholegraph": " (wholegraph schema)",
                            "cache": " (schema from saved cache)",
                            "database": " (schema refreshed from database)",
                        }.get(source, "")
                        st.success(
                            f"✅ Connected successfully! {data['tables_count']} tables, "
                            f"{data['foreign_keys_count']} foreign keys{source_note}."
                        )
                        st.rerun()
                    else:
                        st.error(f"❌ Connection failed: {error}")

# Query Section
else:
    st.success(f"✅ Connected (Connection ID: {st.session_state.connection_id[:8]}...)")
    
    if st.button("Refresh schema from database", help="Re-scan INFORMATION_SCHEMA and update the saved JSON"):
        with st.spinner("Refreshing schema..."):
            ok, payload, err = refresh_schema_from_db(st.session_state.connection_id)
            if ok:
                st.success(
                    f"Schema updated: {payload['tables_count']} tables, "
                    f"{payload['foreign_keys_count']} foreign keys."
                )
            else:
                st.error(f"Refresh failed: {err}")
    
    if st.button("Disconnect", type="secondary"):
        st.session_state.connection_id = None
        st.session_state.last_sql_query = None
        st.rerun()
    
    st.header("Query Database")
    
    # Tabs for different query methods
    tab1, tab2 = st.tabs(["Natural Language Query", "Raw SQL Query"])
    
    with tab1:
        st.markdown("### Ask your question in natural language")
        natural_query = st.text_area(
            "Enter your question",
            placeholder="e.g., Show me top 100 records from caboodle.patientdim",
            height=100
        )
        
        if st.button("Generate & Execute SQL", type="primary", use_container_width=True):
            if natural_query:
                with st.spinner("🤖 LLM is generating SQL query..."):
                    success, data, error = execute_query(natural_query, st.session_state.connection_id)
                    
                    if success:
                        st.session_state.last_sql_query = data['sql_query']
                        
                        # Show explanation
                        if data.get('explanation'):
                            st.info(f"💡 **Explanation:** {data['explanation']}")
                        
                        # Show generated SQL
                        st.markdown("### Generated SQL:")
                        st.code(data['sql_query'], language='sql')
                        
                        # Show results
                        if data['results']:
                            st.markdown(f"### Results ({data['row_count']} rows)")
                            df = pd.DataFrame(data['results'])
                            st.dataframe(df, use_container_width=True)
                            
                            # Download buttons
                            col1, col2 = st.columns(2)
                            with col1:
                                csv = df.to_csv(index=False)
                                st.download_button(
                                    label="Download CSV",
                                    data=csv,
                                    file_name="results.csv",
                                    mime="text/csv",
                                    use_container_width=True
                                )
                            with col2:
                                json_str = json.dumps(data['results'], indent=2)
                                st.download_button(
                                    label="Download JSON",
                                    data=json_str,
                                    file_name="results.json",
                                    mime="application/json",
                                    use_container_width=True
                                )
                        else:
                            st.info("Query executed successfully but returned no results.")
                    else:
                        st.error(f"❌ Query failed: {error}")
            else:
                st.warning("Please enter a question")
    
    with tab2:
        st.markdown("### Write and execute SQL directly")
        sql_query = st.text_area(
            "Enter SQL query",
            value=st.session_state.last_sql_query or "",
            placeholder="SELECT TOP 100 * FROM caboodle.patientdim;",
            height=150
        )
        
        if st.button("Execute SQL", type="primary", use_container_width=True):
            if sql_query:
                with st.spinner("Executing SQL query..."):
                    success, data, error = execute_raw_sql(sql_query, st.session_state.connection_id)
                    
                    if success:
                        st.session_state.last_sql_query = sql_query
                        
                        # Show results
                        if data['results']:
                            st.markdown(f"### Results ({data['row_count']} rows)")
                            df = pd.DataFrame(data['results'])
                            st.dataframe(df, use_container_width=True)
                            
                            # Download buttons
                            col1, col2 = st.columns(2)
                            with col1:
                                csv = df.to_csv(index=False)
                                st.download_button(
                                    label="Download CSV",
                                    data=csv,
                                    file_name="results.csv",
                                    mime="text/csv",
                                    use_container_width=True
                                )
                            with col2:
                                json_str = json.dumps(data['results'], indent=2)
                                st.download_button(
                                    label="Download JSON",
                                    data=json_str,
                                    file_name="results.json",
                                    mime="application/json",
                                    use_container_width=True
                                )
                        else:
                            st.success("Query executed successfully!")
                    else:
                        st.error(f"❌ SQL execution failed: {error}")
            else:
                st.warning("Please enter a SQL query")



