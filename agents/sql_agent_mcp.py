from typing import Dict, Any, List, Optional
import json
import requests
from config.database import DatabaseConfig
from utils.db_connector import DatabaseConnector
import pandas as pd

class SQLMCPAgent:
    """Natural language to SQL Agent using Model Context Protocol (MCP)"""
    
    def __init__(self):
        self.db = DatabaseConnector()
        self.provider = DatabaseConfig.LLM_PROVIDER
        
        # Verify we're using OpenAI provider for MCP
        if self.provider != 'openai':
            raise ValueError("MCP implementation requires OpenAI provider")
        
        # Get database schemas
        self.schemas = self.db.get_all_schemas()
    
    def _format_schemas(self) -> str:
        """Format database schema information"""
        schema_lines = []
        for table_name, schema in self.schemas.items():
            schema_lines.append(f"\nTable: {table_name}")
            schema_lines.append("Columns:")
            for col in schema['columns']:
                nullable = "Nullable" if col['nullable'] else "Not Null"
                schema_lines.append(f"  - {col['name']} ({col['type']}, {nullable})")
            if schema['primary_key']:
                schema_lines.append(f"  Primary Key: {', '.join(schema['primary_key'])}")
        
        return '\n'.join(schema_lines)
    
    def _build_mcp_messages(self, natural_query: str) -> List[Dict[str, Any]]:
        """Build MCP messages for the query"""
        # System message with database schema
        schema_text = self._format_schemas()
        
        system_message = {
            "role": "system",
            "content": f"""You are a professional medical database SQL query assistant. Your task is to convert doctors' natural language queries into accurate SQL statements.

# Database Schema Information:
{schema_text}

# Important Rules:
1. Only generate SELECT queries, prohibit DELETE, UPDATE, DROP and other modification operations
2. Use standard SQL syntax compatible with {DatabaseConfig.DB_TYPE}
3. Consider privacy of medical data, avoid returning too much sensitive information
4. If the query is unclear, generate the most reasonable SQL

When the user asks a question, use the generate_sql_query tool to create appropriate SQL."""
        }
        
        # User message with the query
        user_message = {
            "role": "user",
            "content": f"Please convert the following query to SQL:\n{natural_query}"
        }
        
        return [system_message, user_message]
    
    def _build_mcp_tools(self) -> List[Dict[str, Any]]:
        """Define the MCP tools schema"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "generate_sql_query",
                    "description": "Generate an SQL query based on the user's natural language request",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "sql": {
                                "type": "string",
                                "description": "The SQL query generated from the natural language request"
                            },
                            "explanation": {
                                "type": "string",
                                "description": "Explanation of what the SQL query does"
                            },
                            "tables_used": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Names of database tables used in the query"
                            }
                        },
                        "required": ["sql", "explanation", "tables_used"]
                    }
                }
            }
        ]
    
    def generate_sql(self, natural_query: str) -> Dict[str, Any]:
        """Generate SQL from natural language using MCP"""
        try:
            # Set up the request payload
            payload = {
                "messages": self._build_mcp_messages(natural_query),
                "tools": self._build_mcp_tools(),
                "tool_choice": {"type": "function", "function": {"name": "generate_sql_query"}},
                "model": DatabaseConfig.MODEL_NAME,
                "temperature": 0.1
            }
            
            # Make the request to OpenAI API
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {DatabaseConfig.OPENAI_API_KEY}"
            }
            
            response = requests.post(
                "https://api.openai.com/v1/chat/completions", 
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            response_data = response.json()
            
            # Extract the tool call from response
            message = response_data["choices"][0]["message"]
            tool_calls = message.get("tool_calls", [])
            
            if not tool_calls:
                raise ValueError("No tool calls found in the response")
            
            # Extract the function arguments
            function_call = tool_calls[0]["function"]
            result = json.loads(function_call["arguments"])
            
            # Add confidence score
            result["confidence"] = 0.9
            
            return result
            
        except Exception as e:
            return {
                "sql": "SELECT 'Error generating SQL' AS error_message",
                "explanation": f"Failed to generate SQL: {str(e)}",
                "confidence": 0,
                "tables_used": []
            }
    
    def execute_natural_query(self, natural_query: str) -> Dict[str, Any]:
        """Execute complete natural language query workflow"""
        try:
            # 1. Generate SQL
            sql_result = self.generate_sql(natural_query)
            sql_query = sql_result['sql']
            
            # 2. Validate SQL safety
            if not self.db.validate_query(sql_query):
                return {
                    'success': False,
                    'error': 'Query contains unsafe operations',
                    'sql': sql_query
                }
            
            # 3. Execute query
            df = self.db.execute_query(sql_query)
            
            # 4. Export to CSV
            csv_filename = f"query_result_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv"
            csv_path = self.db.export_to_csv(df, csv_filename)
            
            return {
                'success': True,
                'sql': sql_query,
                'explanation': sql_result.get('explanation', ''),
                'confidence': sql_result.get('confidence', 0),
                'data': df,
                'csv_path': csv_path,
                'row_count': len(df)
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'sql': sql_result.get('sql', '') if 'sql_result' in locals() else None
            }
