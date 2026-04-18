"""
Schema extraction module - extracts table schemas and foreign key relationships
"""
from typing import Dict, List, Any, Optional
from database.connection import DatabaseConnection
import logging

logger = logging.getLogger(__name__)

# Default: only ``activedirectory`` (excludes stg, caboodle, etc.)
DEFAULT_ALLOWED_SCHEMA = "activedirectory"


class SchemaExtractor:
    """Extracts database schema information including tables, columns, and foreign keys"""

    def __init__(
        self,
        db_connection: DatabaseConnection,
        allowed_schema: Optional[str] = DEFAULT_ALLOWED_SCHEMA,
    ):
        self.db_connection = db_connection
        # If None, extract all schemas (previous behavior). Otherwise limit to this schema.
        self.allowed_schema = allowed_schema

    def _schema_predicate_tables(self) -> str:
        if not self.allowed_schema:
            return ""
        lit = self.allowed_schema.replace("'", "''")
        return f" AND t.TABLE_SCHEMA = N'{lit}' "

    def extract_all_schemas(self) -> Dict[str, Any]:
        """Extract complete database schema"""
        return {
            "tables": self.extract_tables(),
            "foreign_keys": self.extract_foreign_keys(),
            "indexes": self.extract_indexes()
        }

    def extract_tables(self) -> List[Dict[str, Any]]:
        """Extract tables (optionally limited to ``allowed_schema``) with their columns"""
        query = f"""
        SELECT 
            t.TABLE_SCHEMA,
            t.TABLE_NAME,
            c.COLUMN_NAME,
            c.DATA_TYPE,
            c.CHARACTER_MAXIMUM_LENGTH,
            c.IS_NULLABLE,
            c.COLUMN_DEFAULT,
            CASE WHEN pk.COLUMN_NAME IS NOT NULL THEN 1 ELSE 0 END AS IS_PRIMARY_KEY
        FROM INFORMATION_SCHEMA.TABLES t
        INNER JOIN INFORMATION_SCHEMA.COLUMNS c ON t.TABLE_NAME = c.TABLE_NAME 
            AND t.TABLE_SCHEMA = c.TABLE_SCHEMA
        LEFT JOIN (
            SELECT ku.TABLE_SCHEMA, ku.TABLE_NAME, ku.COLUMN_NAME
            FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
            INNER JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE ku
                ON tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
                AND tc.CONSTRAINT_NAME = ku.CONSTRAINT_NAME
        ) pk ON c.TABLE_NAME = pk.TABLE_NAME 
            AND c.COLUMN_NAME = pk.COLUMN_NAME
            AND c.TABLE_SCHEMA = pk.TABLE_SCHEMA
        WHERE t.TABLE_TYPE = 'BASE TABLE'
        {self._schema_predicate_tables()}
        ORDER BY t.TABLE_SCHEMA, t.TABLE_NAME, c.ORDINAL_POSITION
        """
        
        try:
            results = self.db_connection.execute_query(query)
            
            # Group by table
            tables_dict = {}
            for row in results:
                table_key = f"{row['TABLE_SCHEMA']}.{row['TABLE_NAME']}"
                
                if table_key not in tables_dict:
                    tables_dict[table_key] = {
                        "schema": row['TABLE_SCHEMA'],
                        "table_name": row['TABLE_NAME'],
                        "full_name": table_key,
                        "columns": []
                    }
                
                tables_dict[table_key]["columns"].append({
                    "name": row['COLUMN_NAME'],
                    "data_type": row['DATA_TYPE'],
                    "max_length": row['CHARACTER_MAXIMUM_LENGTH'],
                    "is_nullable": row['IS_NULLABLE'] == 'YES',
                    "default_value": row['COLUMN_DEFAULT'],
                    "is_primary_key": bool(row['IS_PRIMARY_KEY'])
                })
            
            return list(tables_dict.values())
        except Exception as e:
            logger.error(f"Error extracting tables: {e}")
            raise
    
    def extract_foreign_keys(self) -> List[Dict[str, Any]]:
        """Extract foreign key relationships (both ends in ``allowed_schema`` when set)."""
        where_clause = ""
        if self.allowed_schema:
            lit = self.allowed_schema.replace("'", "''")
            where_clause = (
                f"WHERE fk.TABLE_SCHEMA = N'{lit}' AND pk.TABLE_SCHEMA = N'{lit}' "
            )
        query = f"""
        SELECT 
            fk.TABLE_SCHEMA AS FK_SCHEMA,
            fk.TABLE_NAME AS FK_TABLE,
            fk.COLUMN_NAME AS FK_COLUMN,
            pk.TABLE_SCHEMA AS PK_SCHEMA,
            pk.TABLE_NAME AS PK_TABLE,
            pk.COLUMN_NAME AS PK_COLUMN,
            fk.CONSTRAINT_NAME
        FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS c
        INNER JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE fk
            ON c.CONSTRAINT_NAME = fk.CONSTRAINT_NAME
        INNER JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE pk
            ON c.UNIQUE_CONSTRAINT_NAME = pk.CONSTRAINT_NAME
        {where_clause}
        ORDER BY fk.TABLE_SCHEMA, fk.TABLE_NAME, fk.ORDINAL_POSITION
        """
        
        try:
            results = self.db_connection.execute_query(query)
            
            foreign_keys = []
            for row in results:
                foreign_keys.append({
                    "from_table": f"{row['FK_SCHEMA']}.{row['FK_TABLE']}",
                    "from_column": row['FK_COLUMN'],
                    "to_table": f"{row['PK_SCHEMA']}.{row['PK_TABLE']}",
                    "to_column": row['PK_COLUMN'],
                    "constraint_name": row['CONSTRAINT_NAME']
                })
            
            return foreign_keys
        except Exception as e:
            logger.error(f"Error extracting foreign keys: {e}")
            raise
    
    def extract_indexes(self) -> List[Dict[str, Any]]:
        """Extract index information"""
        # Simplified index extraction - can be enhanced later
        # For now, we'll skip detailed index extraction as it's not critical for LLM
        return []

