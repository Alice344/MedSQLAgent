import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sys
import os

# Add project root directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agents.sql_agent import SQLAgent
from utils.db_connector import DatabaseConnector
from utils.schema_vector_store import SchemaVectorStore

# Page configuration
st.set_page_config(
    page_title="Medical Database Query System",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #1f77b4;
        text-align: center;
        padding: 1rem 0;
    }
    .info-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #f0f2f6;
        margin: 1rem 0;
    }
    .success-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #d4edda;
        border-left: 5px solid #28a745;
    }
    .error-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #f8d7da;
        border-left: 5px solid #dc3545;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.db_type = None
    st.session_state.connection_info = None

if 'query_history' not in st.session_state:
    st.session_state.query_history = []

if 'agent' not in st.session_state:
    st.session_state.agent = None
    st.session_state.db = None
    st.session_state.initialized = False

# Main header
st.markdown('<h1 class="main-header">🏥 Medical Database Intelligent Query System</h1>', unsafe_allow_html=True)

# Login page for Caboodle
if not st.session_state.logged_in:
    st.markdown("## 🔐 Database Connection")
    
    # Database type selection
    db_type = st.selectbox(
        "Select Database Type",
        ["Caboodle (SQL Server)", "MySQL", "PostgreSQL", "SQLite"],
        key="db_type_select"
    )
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Connection Settings")
        
        # Initialize use_azure_ad for all database types
        use_azure_ad = False
        
        if db_type == "Caboodle (SQL Server)":
            # Authentication method selection
            auth_method = st.radio(
                "Authentication Method",
                ["Azure AD Interactive (Recommended for Caboodle)", "SQL Server Authentication"],
                key="caboodle_auth_method"
            )
            
            host = st.text_input("Server Host", value="", key="caboodle_host", placeholder="e.g., caboodle.example.com")
            database = st.text_input("Database Name", value="", key="caboodle_db", placeholder="Caboodle database name")
            driver = st.selectbox(
                "ODBC Driver",
                ["ODBC Driver 17 for SQL Server", "ODBC Driver 18 for SQL Server", "SQL Server Native Client 11.0"],
                key="caboodle_driver"
            )
            
            if auth_method == "Azure AD Interactive (Recommended for Caboodle)":
                username = st.text_input("Username (Email)", value="", key="caboodle_user", 
                                        placeholder="your.email@domain.com")
                password = None  # Not needed for Azure AD Interactive
                port = None  # Not needed for Azure AD
                use_azure_ad = True
            else:
                port = st.number_input("Port", value=1433, min_value=1, max_value=65535, key="caboodle_port")
                username = st.text_input("Username", value="", key="caboodle_user")
                password = st.text_input("Password", type="password", value="", key="caboodle_pass")
                use_azure_ad = False
            
            db_type_code = "caboodle"
            
        elif db_type == "MySQL":
            host = st.text_input("Host", value="localhost", key="mysql_host")
            port = st.number_input("Port", value=3306, min_value=1, max_value=65535, key="mysql_port")
            database = st.text_input("Database Name", value="hospital_db", key="mysql_db")
            username = st.text_input("Username", value="root", key="mysql_user")
            password = st.text_input("Password", type="password", value="", key="mysql_pass")
            driver = None
            db_type_code = "mysql"
            
        elif db_type == "PostgreSQL":
            host = st.text_input("Host", value="localhost", key="postgres_host")
            port = st.number_input("Port", value=5432, min_value=1, max_value=65535, key="postgres_port")
            database = st.text_input("Database Name", value="hospital_db", key="postgres_db")
            username = st.text_input("Username", value="postgres", key="postgres_user")
            password = st.text_input("Password", type="password", value="", key="postgres_pass")
            driver = None
            db_type_code = "postgresql"
            
        else:  # SQLite
            database = st.text_input("Database Path", value="./data/hospital.db", key="sqlite_path")
            host = None
            port = None
            username = None
            password = None
            driver = None
            db_type_code = "sqlite"
    
    with col2:
        st.subheader("Connection Info")
        st.info("""
        **Instructions:**
        1. Enter your database connection credentials
        2. Click 'Connect' to establish connection
        3. After successful connection, all table schemas will be indexed in vector database
        4. You can then use natural language to query the database
        """)
        
        if db_type == "Caboodle (SQL Server)":
            st.warning("""
            **Caboodle Connection:**
            - For Azure AD Interactive: You'll be prompted to authenticate in a browser window
            - Ensure you have the correct ODBC driver installed
            - The system will index all accessible tables after login
            - Azure AD Interactive is recommended for Caboodle connections
            """)
    
    # Connect button
    if st.button("🔌 Connect to Database", type="primary", use_container_width=True):
        if db_type_code == "sqlite":
            if not database:
                st.error("Please enter database path")
            else:
                try:
                    with st.spinner("Connecting to database and indexing schemas..."):
                        db = DatabaseConnector(
                            db_type=db_type_code,
                            database=database
                        )
                        
                        # Get all schemas
                        schemas = db.get_all_schemas()
                        
                        if not schemas:
                            st.warning("⚠️ No tables found in the database")
                        else:
                            # Create vector store and index schemas
                            vector_store = SchemaVectorStore()
                            vector_store.clear()  # Clear any existing data
                            vector_store.add_schemas(schemas)
                            
                            # Initialize SQL agent
                            agent = SQLAgent(db=db, vector_store=vector_store, use_vector_search=True)
                            
                            st.session_state.db = db
                            st.session_state.agent = agent
                            st.session_state.db_type = db_type_code
                            st.session_state.connection_info = {
                                'database': database
                            }
                            st.session_state.logged_in = True
                            st.session_state.initialized = True
                            
                            st.success(f"✅ Connected successfully! Indexed {len(schemas)} tables.")
                            st.info(f"📊 Found {len(schemas)} tables. All schemas have been indexed in vector database.")
                except Exception as e:
                    st.error(f"❌ Connection failed: {str(e)}")
                    import traceback
                    st.code(traceback.format_exc())
        else:
            # Validate required fields based on authentication method
            if db_type_code == "caboodle" and use_azure_ad:
                # Azure AD validation
                if not host or not database or not username:
                    st.error("Please fill in Server Host, Database Name, and Username")
                else:
                    try:
                        with st.spinner("Connecting to database with Azure AD Interactive authentication...\nYou may be prompted to authenticate in a browser window."):
                            # Create Azure AD connection
                            db = DatabaseConnector.create_azure_ad_connection(
                                server=host,
                                database=database,
                                username=username,
                                driver=driver
                            )
                            
                            # Get all schemas
                            schemas = db.get_all_schemas()
                            
                            if not schemas:
                                st.warning("⚠️ No tables found in the database")
                            else:
                                # Create vector store and index schemas
                                vector_store = SchemaVectorStore()
                                vector_store.clear()  # Clear any existing data
                                vector_store.add_schemas(schemas)
                                
                                # Initialize SQL agent
                                agent = SQLAgent(db=db, vector_store=vector_store, use_vector_search=True)
                                
                                st.session_state.db = db
                                st.session_state.agent = agent
                                st.session_state.db_type = db_type_code
                                st.session_state.connection_info = {
                                    'host': host,
                                    'database': database,
                                    'username': username,
                                    'auth_method': 'Azure AD Interactive'
                                }
                                st.session_state.logged_in = True
                                st.session_state.initialized = True
                                
                                st.success(f"✅ Connected successfully! Indexed {len(schemas)} tables.")
                                st.info(f"📊 Found {len(schemas)} tables. All schemas have been indexed in vector database.")
                                
                    except Exception as e:
                        st.error(f"❌ Connection failed: {str(e)}")
                        import traceback
                        st.code(traceback.format_exc())
            else:
                # Standard authentication validation
                if not host or not database or not username or not password:
                    st.error("Please fill in all required fields")
                else:
                    try:
                        with st.spinner("Connecting to database and indexing schemas..."):
                            # Create database connection
                            db = DatabaseConnector(
                                db_type=db_type_code,
                                host=host,
                                port=port,
                                user=username,
                                password=password,
                                database=database,
                                driver=driver if db_type_code == "caboodle" else None
                            )
                        
                        # Get all schemas
                        schemas = db.get_all_schemas()
                        
                        if not schemas:
                            st.warning("⚠️ No tables found in the database")
                        else:
                            # Create vector store and index schemas
                            vector_store = SchemaVectorStore()
                            vector_store.clear()  # Clear any existing data
                            vector_store.add_schemas(schemas)
                            
                            # Initialize SQL agent
                            agent = SQLAgent(db=db, vector_store=vector_store, use_vector_search=True)
                            
                            st.session_state.db = db
                            st.session_state.agent = agent
                            st.session_state.db_type = db_type_code
                            st.session_state.connection_info = {
                                'host': host,
                                'database': database,
                                'username': username
                            }
                            st.session_state.logged_in = True
                            st.session_state.initialized = True
                            
                            st.success(f"✅ Connected successfully! Indexed {len(schemas)} tables.")
                            st.info(f"📊 Found {len(schemas)} tables. All schemas have been indexed in vector database.")
                            
                except Exception as e:
                    st.error(f"❌ Connection failed: {str(e)}")
                    import traceback
                    st.code(traceback.format_exc())
    
    st.stop()

# Initialize agent if not already done
if st.session_state.logged_in and not st.session_state.initialized:
    try:
        if st.session_state.db:
            vector_store = SchemaVectorStore()
            schemas = st.session_state.db.get_all_schemas()
            if schemas:
                vector_store.clear()
                vector_store.add_schemas(schemas)
            st.session_state.agent = SQLAgent(db=st.session_state.db, vector_store=vector_store, use_vector_search=True)
            st.session_state.initialized = True
    except Exception as e:
        st.error(f"Initialization failed: {str(e)}")
        st.session_state.initialized = False

# Sidebar
with st.sidebar:
    st.header("📊 Database Information")
    
    if st.session_state.initialized:
        # Display database tables
        tables = st.session_state.db.get_table_names()
        st.subheader(f"Available Tables ({len(tables)})")
        
        selected_table = st.selectbox("Select table to view schema", tables)
        
        if selected_table:
            schema = st.session_state.db.get_table_schema(selected_table)
            st.write("**Column Information:**")
            for col in schema['columns']:
                st.text(f"• {col['name']} ({col['type']})")
            
            if st.button("View Sample Data"):
                sample_df = st.session_state.db.get_sample_data(selected_table)
                st.dataframe(sample_df)
    
    st.divider()
    
    # Query history
    st.subheader("📝 Query History")
    if st.session_state.query_history:
        for i, query in enumerate(reversed(st.session_state.query_history[-5:])):
            with st.expander(f"Query {len(st.session_state.query_history) - i}"):
                st.text(query['natural_query'])
                st.code(query['sql'], language='sql')
    else:
        st.info("No query history yet")

# Main content area
if not st.session_state.initialized:
    st.error("⚠️ System not properly initialized, please check database connection configuration")
    st.stop()

# Create tabs
tab1, tab2, tab3 = st.tabs(["💬 Smart Query", "📈 Data Visualization", "⚙️ System Settings"])

with tab1:
    st.header("Natural Language Query")
    
    # Query examples
    with st.expander("💡 Query Examples", expanded=False):
        st.markdown("""
        - Find patients admitted in the last week
        - Count the number of patients in each department
        - Find diabetic patients over 60 years old
        - Query all patients under a specific doctor's care
        - Calculate incidence rates for various diseases
        """)
    
    # Query input
    natural_query = st.text_area(
        "Describe your query in natural language:",
        height=100,
        placeholder="Example: Find all hospitalized patients in the last month"
    )
    
    col1, col2 = st.columns([1, 5])
    with col1:
        execute_button = st.button("🚀 Execute Query", type="primary", use_container_width=True)
    with col2:
        if st.button("🗑️ Clear History", use_container_width=True):
            st.session_state.query_history = []
            st.rerun()
    
    if execute_button and natural_query:
        with st.spinner("🤔 Understanding your query..."):
            result = st.session_state.agent.execute_natural_query(natural_query)
        
        if result['success']:
            # Success result
            st.markdown('<div class="success-box">', unsafe_allow_html=True)
            st.success("✅ Query executed successfully!")
            st.markdown('</div>', unsafe_allow_html=True)
            
            # Display explanation
            st.subheader("📖 Query Explanation")
            st.info(result['explanation'])
            
            # Display generated SQL
            st.subheader("🔧 Generated SQL")
            st.code(result['sql'], language='sql')
            
            # Display confidence
            confidence = result.get('confidence', 0)
            st.metric("Confidence", f"{confidence:.0%}")
            
            # Display results
            st.subheader(f"📊 Query Results ({result['row_count']} rows)")
            st.dataframe(result['data'], use_container_width=True)
            
            # Download button
            csv = result['data'].to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                label="📥 Download CSV File",
                data=csv,
                file_name=f"query_result.csv",
                mime="text/csv"
            )
            
            st.success(f"✅ CSV file saved to: {result['csv_path']}")
            
            # Save to history
            st.session_state.query_history.append({
                'natural_query': natural_query,
                'sql': result['sql'],
                'row_count': result['row_count']
            })
            
        else:
            # Error result
            st.markdown('<div class="error-box">', unsafe_allow_html=True)
            st.error(f"❌ Query execution failed: {result['error']}")
            st.markdown('</div>', unsafe_allow_html=True)
            
            if result.get('sql'):
                st.subheader("Generated SQL (may contain errors)")
                st.code(result['sql'], language='sql')

with tab2:
    st.header("Data Visualization")
    
    if st.session_state.query_history:
        st.info("📌 First execute a query in the 'Smart Query' tab, then visualize the results here")
        
        # Get the last query result
        if st.button("Visualize Last Query Result"):
            # Re-execute the last query
            last_query = st.session_state.query_history[-1]
            result = st.session_state.agent.execute_natural_query(last_query['natural_query'])
            
            if result['success'] and not result['data'].empty:
                df = result['data']
                
                # Select visualization type
                viz_type = st.selectbox(
                    "Select Chart Type",
                    ["Bar Chart", "Line Chart", "Pie Chart", "Scatter Plot", "Box Plot"]
                )
                
                numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
                categorical_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
                
                if viz_type == "Bar Chart" and categorical_cols and numeric_cols:
                    x_col = st.selectbox("X-axis (Categorical)", categorical_cols)
                    y_col = st.selectbox("Y-axis (Numeric)", numeric_cols)
                    fig = px.bar(df, x=x_col, y=y_col, title=f"{y_col} by {x_col}")
                    st.plotly_chart(fig, use_container_width=True)
                
                elif viz_type == "Pie Chart" and categorical_cols:
                    col = st.selectbox("Select Categorical Column", categorical_cols)
                    value_counts = df[col].value_counts()
                    fig = px.pie(values=value_counts.values, names=value_counts.index, 
                                title=f"{col} Distribution")
                    st.plotly_chart(fig, use_container_width=True)
                
                elif viz_type == "Line Chart" and numeric_cols:
                    y_col = st.selectbox("Y-axis", numeric_cols)
                    fig = px.line(df, y=y_col, title=f"{y_col} Trend")
                    st.plotly_chart(fig, use_container_width=True)
                
                else:
                    st.warning("Data type not suitable for selected chart type")
    else:
        st.info("No query results available for visualization")

with tab3:
    st.header("System Settings")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📊 Database Statistics")
        if st.session_state.initialized:
            tables = st.session_state.db.get_table_names()
            st.metric("Number of Tables", len(tables))
            st.metric("Total Queries", len(st.session_state.query_history))
            if st.session_state.agent and st.session_state.agent.vector_store:
                st.metric("Indexed Schemas", len(st.session_state.agent.vector_store.metadata))
    
    with col2:
        st.subheader("🔧 Configuration Info")
        if st.session_state.initialized:
            st.text(f"Database Type: {st.session_state.db_type}")
            if st.session_state.connection_info:
                st.text(f"Host: {st.session_state.connection_info.get('host', 'N/A')}")
                st.text(f"Database: {st.session_state.connection_info.get('database', 'N/A')}")
            st.text(f"LLM Provider: {st.session_state.agent.provider}")
            st.text(f"Model: {st.session_state.agent.model}")
            st.text(f"Vector Search: {'Enabled' if st.session_state.agent.use_vector_search else 'Disabled'}")
    
    st.divider()
    
    col3, col4 = st.columns(2)
    
    with col3:
        if st.button("🔄 Refresh Schemas"):
            if st.session_state.initialized:
                try:
                    with st.spinner("Refreshing schemas..."):
                        st.session_state.agent.refresh_schemas()
                        st.success("✅ Schemas refreshed successfully!")
                        st.rerun()
                except Exception as e:
                    st.error(f"❌ Refresh failed: {str(e)}")
            else:
                st.warning("Please connect to database first")
    
    with col4:
        if st.button("🚪 Disconnect"):
            st.session_state.logged_in = False
            st.session_state.initialized = False
            st.session_state.agent = None
            st.session_state.db = None
            st.session_state.connection_info = None
            st.rerun()

# Footer
st.divider()
st.markdown("""
<div style='text-align: center; color: #666; padding: 1rem;'>
    <p>🏥 Medical Database Intelligent Query System | Natural Language SQL Query powered by LLM</p>
</div>
""", unsafe_allow_html=True)