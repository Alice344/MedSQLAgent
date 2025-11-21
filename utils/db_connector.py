from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.engine import URL
import pandas as pd
from typing import List, Dict, Any, Optional
from urllib.parse import quote_plus
import pyodbc
from config.database import DatabaseConfig

class DatabaseConnector:
    """Database connection and operation class"""
    
    def __init__(self, connection_string: Optional[str] = None, db_type: Optional[str] = None, 
                 host: Optional[str] = None, port: Optional[int] = None, 
                 user: Optional[str] = None, password: Optional[str] = None, 
                 database: Optional[str] = None, driver: Optional[str] = None,
                 use_azure_ad: bool = False):
        """
        Initialize database connector with optional custom connection parameters
        
        Args:
            connection_string: Direct connection string (overrides other params)
            db_type: Database type (mysql, postgresql, sqlite, sqlserver, caboodle)
            host: Database host
            port: Database port
            user: Database username
            password: Database password
            database: Database name
            driver: ODBC driver name (for SQL Server/Caboodle)
            use_azure_ad: Use Azure AD Interactive authentication (for Caboodle)
        """
        self.engine = None
        self.use_azure_ad = use_azure_ad
        self.pyodbc_conn = None
        
        if connection_string:
            self.connection_string = connection_string
        else:
            self.connection_string = self._build_connection_string(
                db_type, host, port, user, password, database, driver, use_azure_ad
            )
        self._connect()
    
    def _build_connection_string(self, db_type: Optional[str], host: Optional[str], 
                                 port: Optional[int], user: Optional[str], 
                                 password: Optional[str], database: Optional[str],
                                 driver: Optional[str] = None, use_azure_ad: bool = False) -> str:
        """Build connection string from parameters"""
        if db_type:
            if db_type == 'sqlserver' or db_type == 'caboodle':
                if use_azure_ad:
                    # For Azure AD, we'll use pyodbc directly, return a placeholder
                    # The actual connection will be handled in _connect()
                    return "azure_ad_connection"
                else:
                    # Standard SQL Server authentication
                    if driver is None:
                        driver = DatabaseConfig.SQLSERVER_CONFIG.get('driver', 'ODBC Driver 17 for SQL Server')
                    driver_encoded = quote_plus(driver)
                    password_encoded = quote_plus(password) if password else ''
                    return f"mssql+pyodbc://{user}:{password_encoded}@{host}:{port}/{database}?driver={driver_encoded}"
            elif db_type == 'mysql':
                password_encoded = quote_plus(password) if password else ''
                return f"mysql+pymysql://{user}:{password_encoded}@{host}:{port}/{database}?charset=utf8mb4"
            elif db_type == 'postgresql':
                password_encoded = quote_plus(password) if password else ''
                return f"postgresql+psycopg2://{user}:{password_encoded}@{host}:{port}/{database}"
            elif db_type == 'sqlite':
                return f"sqlite:///{database}"
        return DatabaseConfig.get_connection_string()
    
    def _connect(self):
        """Establish database connection"""
        try:
            if self.use_azure_ad and self.connection_string == "azure_ad_connection":
                # Azure AD Interactive authentication
                # We need to get connection params from the instance
                # This will be set up in the Streamlit app
                raise ValueError("Azure AD connection requires connection parameters")
            else:
                self.engine = create_engine(self.connection_string, echo=False)
                # Test connection
                with self.engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
            print("✓ Database connected successfully")
        except Exception as e:
            print(f"✗ Database connection failed: {str(e)}")
            raise
    
    @staticmethod
    def create_azure_ad_connection(server: str, database: str, username: str, 
                                   driver: str = "ODBC Driver 17 for SQL Server"):
        """
        Create Azure AD Interactive connection
        
        Args:
            server: Server hostname
            database: Database name
            username: Username (for UID)
            driver: ODBC driver name
            
        Returns:
            DatabaseConnector instance with Azure AD connection
        """
        # Build ODBC connection string for Azure AD (same format as user's example)
        odbc_conn_str = f"""DRIVER={{{driver}}};SERVER={server};DATABASE={database};UID={username};Authentication=ActiveDirectoryInteractive;"""
        
        # Create SQLAlchemy connection URL using odbc_connect parameter
        connection_url = URL.create(
            "mssql+pyodbc",
            query={"odbc_connect": odbc_conn_str}
        )
        
        # Create connector instance
        connector = DatabaseConnector.__new__(DatabaseConnector)
        
        # Create engine with a creator function that uses pyodbc directly
        def create_connection():
            return pyodbc.connect(odbc_conn_str, autocommit=True)
        
        connector.engine = create_engine(
            connection_url, 
            creator=create_connection,
            echo=False
        )
        connector.use_azure_ad = True
        connector.pyodbc_conn = None  # Connection will be created on demand
        
        # Test connection
        with connector.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        
        print("✓ Azure AD database connected successfully")
        return connector
    
    def get_table_names(self) -> List[str]:
        """Get all table names"""
        inspector = inspect(self.engine)
        return inspector.get_table_names()
    
    def get_table_schema(self, table_name: str) -> Dict[str, Any]:
        """Get table schema information"""
        inspector = inspect(self.engine)
        columns = inspector.get_columns(table_name)
        pk = inspector.get_pk_constraint(table_name)
        
        schema = {
            'table_name': table_name,
            'columns': [],
            'primary_key': pk.get('constrained_columns', [])
        }
        
        for col in columns:
            schema['columns'].append({
                'name': col['name'],
                'type': str(col['type']),
                'nullable': col['nullable'],
                'default': col.get('default')
            })
        
        return schema
    
    def get_all_schemas(self) -> Dict[str, Dict]:
        """Get schema information for all tables"""
        tables = self.get_table_names()
        schemas = {}
        for table in tables:
            schemas[table] = self.get_table_schema(table)
        return schemas
    
    def execute_query(self, query: str) -> pd.DataFrame:
        """Execute SQL query and return DataFrame"""
        try:
            with self.engine.connect() as conn:
                result = pd.read_sql(text(query), conn)
            return result
        except SQLAlchemyError as e:
            raise Exception(f"SQL execution error: {str(e)}")
    
    def get_sample_data(self, table_name: str, limit: int = 5) -> pd.DataFrame:
        """Get sample data from table"""
        # Handle different SQL dialects for LIMIT
        db_type = DatabaseConfig.DB_TYPE
        if db_type in ['sqlserver', 'caboodle']:
            query = f"SELECT TOP {limit} * FROM {table_name}"
        else:
            query = f"SELECT * FROM {table_name} LIMIT {limit}"
        return self.execute_query(query)
    
    def export_to_csv(self, df: pd.DataFrame, filename: str) -> str:
        """Export DataFrame to CSV"""
        import os
        os.makedirs(DatabaseConfig.EXPORT_DIR, exist_ok=True)
        filepath = os.path.join(DatabaseConfig.EXPORT_DIR, filename)
        df.to_csv(filepath, index=False, encoding='utf-8-sig')
        return filepath
    
    def validate_query(self, query: str) -> bool:
        """Validate SQL query safety"""
        # Basic security check
        dangerous_keywords = ['DROP', 'DELETE', 'TRUNCATE', 'ALTER', 'UPDATE', 'INSERT']
        query_upper = query.upper()
        
        for keyword in dangerous_keywords:
            if keyword in query_upper:
                return False
        return True
    
    def close(self):
        """Close database connection"""
        if self.engine:
            self.engine.dispose()