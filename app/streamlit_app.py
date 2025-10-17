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
if 'agent' not in st.session_state:
    try:
        st.session_state.agent = SQLAgent()
        st.session_state.db = st.session_state.agent.db
        st.session_state.initialized = True
    except Exception as e:
        st.error(f"Initialization failed: {str(e)}")
        st.session_state.initialized = False

if 'query_history' not in st.session_state:
    st.session_state.query_history = []

# Main header
st.markdown('<h1 class="main-header">🏥 Medical Database Intelligent Query System</h1>', unsafe_allow_html=True)

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
    
    with col2:
        st.subheader("🔧 Configuration Info")
        st.text(f"LLM Provider: {st.session_state.agent.provider}")
        st.text(f"Model: {st.session_state.agent.model}")
    
    st.divider()
    
    if st.button("🔄 Reconnect Database"):
        try:
            st.session_state.agent = SQLAgent()
            st.session_state.db = st.session_state.agent.db
            st.success("✅ Reconnected successfully!")
        except Exception as e:
            st.error(f"❌ Reconnection failed: {str(e)}")

# Footer
st.divider()
st.markdown("""
<div style='text-align: center; color: #666; padding: 1rem;'>
    <p>🏥 Medical Database Intelligent Query System | Natural Language SQL Query powered by LLM</p>
</div>
""", unsafe_allow_html=True)