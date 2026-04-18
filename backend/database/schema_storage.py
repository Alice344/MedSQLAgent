"""
Schema storage module - stores and retrieves database schemas
"""
import json
import os
from typing import Dict, Any, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class SchemaStorage:
    """Manages storage and retrieval of database schemas"""
    
    def __init__(self, storage_dir: str = "schemas"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(exist_ok=True)
    
    def _get_schema_file_path(self, connection_id: str) -> Path:
        """Get file path for a connection's schema"""
        return self.storage_dir / f"{connection_id}.json"
    
    def save_schema(self, connection_id: str, schema: Dict[str, Any]) -> bool:
        """Save schema to file"""
        try:
            file_path = self._get_schema_file_path(connection_id)
            with open(file_path, 'w') as f:
                json.dump(schema, f, indent=2)
            logger.info(f"Schema saved for connection: {connection_id}")
            return True
        except Exception as e:
            logger.error(f"Error saving schema: {e}")
            return False
    
    def load_schema(self, connection_id: str) -> Optional[Dict[str, Any]]:
        """Load schema from file"""
        try:
            file_path = self._get_schema_file_path(connection_id)
            if not file_path.exists():
                return None
            
            with open(file_path, 'r') as f:
                schema = json.load(f)
            logger.info(f"Schema loaded for connection: {connection_id}")
            return schema
        except Exception as e:
            logger.error(f"Error loading schema: {e}")
            return None
    
    def delete_schema(self, connection_id: str) -> bool:
        """Delete schema file"""
        try:
            file_path = self._get_schema_file_path(connection_id)
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Schema deleted for connection: {connection_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting schema: {e}")
            return False
    
    def format_schema_for_llm(self, schema: Dict[str, Any]) -> str:
        """Format schema in a way that's easy for LLM to understand"""
        formatted = []

        # Format tables
        formatted.append("=== DATABASE SCHEMA ===\n")
        for table in schema.get("tables", []):
            table_line = f"\nTable: {table['full_name']}"
            table_desc = table.get("description", "")
            if table_desc:
                table_line += f"  -- {table_desc}"
            formatted.append(table_line)
            formatted.append("Columns:")
            for col in table["columns"]:
                pk_marker = " [PRIMARY KEY]" if col["is_primary_key"] else ""
                nullable = "NULL" if col["is_nullable"] else "NOT NULL"
                col_line = f"  - {col['name']}: {col['data_type']} {nullable}{pk_marker}"
                col_desc = col.get("description", "")
                if col_desc:
                    col_line += f"  -- {col_desc}"
                formatted.append(col_line)

        # Format foreign keys
        formatted.append("\n=== FOREIGN KEY RELATIONSHIPS ===\n")
        for fk in schema.get("foreign_keys", []):
            formatted.append(
                f"{fk['from_table']}.{fk['from_column']} -> "
                f"{fk['to_table']}.{fk['to_column']}"
            )

        return "\n".join(formatted)



