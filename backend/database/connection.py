"""
Database connection module for SQL Server
"""
import pyodbc
from typing import Optional, Dict, List, Any
from contextlib import contextmanager
import logging
import os

logger = logging.getLogger(__name__)

# ── Connection pooling ───────────────────────────────────────────────────────
# pyodbc uses ODBC driver-level connection pooling.  Enable it once at import
# time so every `pyodbc.connect()` call benefits automatically.
pyodbc.pooling = True

# Maximum connections the pool will keep open (default is per-driver).
# Set via env var; 0 = use driver default.
_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "20"))


class DatabaseConnection:
    """Manages SQL Server database connections"""
    
    def __init__(self, server: str, database: str, username: str = None, password: str = None, 
                 port: int = 1433, auth_method: str = "sql", use_mfa: bool = False):
        self.server = server
        self.database = database
        self.username = username
        self.password = password
        self.port = port
        self.auth_method = auth_method  # 'sql' or 'azure_ad'
        self.use_mfa = use_mfa  # Use ActiveDirectoryInteractive for MFA
        self.connection_string = self._build_connection_string()
    
    def _build_connection_string(self) -> str:
        """Build SQL Server connection string"""
        # Try different driver names in order of preference
        drivers_to_try = [
            "ODBC Driver 17 for SQL Server",
            "ODBC Driver 18 for SQL Server",
            "SQL Server",
            "SQL Server Native Client 11.0"
        ]
        
        # For now, use the most common one
        driver = drivers_to_try[0]
        
        # Build base connection string
        if self.auth_method == "azure_ad" or self.use_mfa:
            # Azure AD authentication (with or without MFA)
            if self.use_mfa:
                # ActiveDirectoryInteractive - opens browser for MFA
                auth = "ActiveDirectoryInteractive"
            else:
                # ActiveDirectoryPassword - uses username/password
                auth = "ActiveDirectoryPassword"
            
            # For Azure AD, don't include port in SERVER (use format: server.database.windows.net)
            # Server should already include the full server name without port
            conn_str = (
                f"DRIVER={{{driver}}};"
                f"SERVER={self.server};"
                f"DATABASE={self.database};"
                f"UID={self.username};"
                f"Authentication={auth};"
            )
            
            if self.password and auth == "ActiveDirectoryPassword":
                conn_str += f"PWD={self.password};"
            
            # Note: Encrypt=yes is default for Azure AD, but we can be explicit
            # Don't add TrustServerCertificate for Azure AD
        else:
            # SQL Server authentication
            conn_str = (
                f"DRIVER={{{driver}}};"
                f"SERVER={self.server},{self.port};"
                f"DATABASE={self.database};"
                f"UID={self.username};"
                f"PWD={self.password};"
                f"TrustServerCertificate=yes;"
                f"Encrypt=yes;"
            )
        
        return conn_str
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = None
        try:
            # For Azure AD Interactive, we need autocommit=True
            if self.use_mfa or self.auth_method == "azure_ad":
                conn = pyodbc.connect(self.connection_string, timeout=30, autocommit=True)
            else:
                conn = pyodbc.connect(self.connection_string, timeout=10)
            yield conn
        except pyodbc.Error as e:
            error_msg = str(e)
            logger.error(f"Database connection error: {error_msg}")
            # Provide more specific error information
            if "IM002" in error_msg:
                raise Exception(f"ODBC Driver not found. Please install ODBC Driver 17 for SQL Server. Original error: {error_msg}")
            elif "28000" in error_msg or "login" in error_msg.lower() or "authentication" in error_msg.lower():
                if self.use_mfa:
                    raise Exception(f"Azure AD authentication failed. Please check your credentials and complete MFA in the browser window. Original error: {error_msg}")
                else:
                    raise Exception(f"Authentication failed. Please check username and password. Original error: {error_msg}")
            elif "08001" in error_msg:
                raise Exception(f"Cannot connect to server. Please check server name and network connectivity. Original error: {error_msg}")
            else:
                raise Exception(f"Database connection failed: {error_msg}")
        except Exception as e:
            logger.error(f"Unexpected connection error: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    def test_connection(self) -> bool:
        """Test if database connection works"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                return True
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False
    
    def execute_query(self, query: str, max_rows: int = 10000) -> List[Dict[str, Any]]:
        """Execute a SQL query and return results as list of dictionaries"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            conn.timeout = 120  # 2 minute query timeout
            
            # Handle different query types
            query_upper = query.strip().upper()
            
            # For SELECT queries, fetch results
            if query_upper.startswith('SELECT'):
                cursor.execute(query)
                
                # Get column names
                if cursor.description:
                    columns = [column[0] for column in cursor.description]
                    
                    # Fetch rows with a safety limit to prevent OOM
                    rows = cursor.fetchmany(max_rows)
                    
                    # Convert to list of dictionaries
                    results = [dict(zip(columns, row)) for row in rows]
                    return results
                else:
                    return []
            
            # For INSERT, UPDATE, DELETE, etc. - execute and return affected rows
            else:
                cursor.execute(query)
                conn.commit() if not self.use_mfa else None  # Azure AD uses autocommit
                
                # Try to get affected rows count
                try:
                    rows_affected = cursor.rowcount
                    return [{"rows_affected": rows_affected, "message": "Query executed successfully"}]
                except:
                    return [{"message": "Query executed successfully"}]
    
    def execute_query_pandas(self, query: str):
        """Execute query and return pandas DataFrame (requires pandas)"""
        try:
            import pandas as pd
            with self.get_connection() as conn:
                return pd.read_sql(query, conn)
        except ImportError:
            raise ImportError("pandas is required for this method. Install it with: pip install pandas")

