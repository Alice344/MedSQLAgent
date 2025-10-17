from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import SQLAlchemyError
import pandas as pd
from typing import List, Dict, Any, Optional
from config.database import DatabaseConfig

class DatabaseConnector:
    """Database connection and operation class"""
    
    def __init__(self):
        self.engine = None
        self.connection_string = DatabaseConfig.get_connection_string()
        self._connect()
    
    def _connect(self):
        """Establish database connection"""
        try:
            self.engine = create_engine(self.connection_string, echo=False)
            # Test connection
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("✓ Database connected successfully")
        except Exception as e:
            print(f"✗ Database connection failed: {str(e)}")
            raise
    
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