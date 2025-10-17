from typing import Dict, Any, Optional
import json
import requests
from openai import OpenAI
from anthropic import Anthropic, HUMAN_PROMPT, AI_PROMPT
from config.database import DatabaseConfig
from utils.db_connector import DatabaseConnector
import pandas as pd

class SQLFunctionCallingAgent:
    """Natural language to SQL Agent using Function Calling"""
    
    def __init__(self):
        self.db = DatabaseConnector()
        self.provider = DatabaseConfig.LLM_PROVIDER
        
        # Initialize LLM client
        if self.provider == 'openai':
            self.client = OpenAI(api_key=DatabaseConfig.OPENAI_API_KEY)
            self.model = DatabaseConfig.MODEL_NAME
        elif self.provider == 'anthropic':
            self.client = Anthropic(api_key=DatabaseConfig.ANTHROPIC_API_KEY)
            self.model = 'claude-3-opus-20240229'  # Use an Anthropic model that supports tools
        else:
            raise ValueError(f"Function calling not supported for provider: {self.provider}")
        
        # Get database schemas
        self.schemas = self.db.get_all_schemas()
    
    def _build_system_prompt(self) -> str:
        """Build system prompt"""
        schema_text = self._format_schemas()
        
        return f"""You are a professional medical database SQL query assistant. Your task is to convert doctors' natural language queries into accurate SQL statements.

# Database Schema Information:
{schema_text}

# Important Rules:
1. Only generate SELECT queries, prohibit DELETE, UPDATE, DROP and other modification operations
2. Use standard SQL syntax compatible with {DatabaseConfig.DB_TYPE}
3. Consider privacy of medical data, avoid returning too much sensitive information
4. If the query is unclear, generate the most reasonable SQL

Use the provided function to generate SQL queries."""
    
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
    
    def _get_openai_function_schema(self):
        """Define the OpenAI function schema"""
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
    
    def _get_anthropic_tools_schema(self):
        """Define the Anthropic tools schema"""
        return [
            {
                "name": "generate_sql_query",
                "description": "Generate an SQL query based on the user's natural language request",
                "input_schema": {
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
        ]
    
    def generate_sql(self, natural_query: str) -> Dict[str, Any]:
        """Generate SQL from natural language using function calling"""
        
        if self.provider == 'openai':
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._build_system_prompt()},
                    {"role": "user", "content": f"Please convert the following query to SQL:\n{natural_query}"}
                ],
                tools=self._get_openai_function_schema(),
                tool_choice={"type": "function", "function": {"name": "generate_sql_query"}}
            )
            
            # Extract the function call
            function_call = response.choices[0].message.tool_calls[0].function
            result = json.loads(function_call.arguments)
            # Add confidence score since it's expected in the existing code
            result['confidence'] = 0.9
        
        elif self.provider == 'anthropic':
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                system=self._build_system_prompt(),
                messages=[
                    {"role": "user", "content": f"Please convert the following query to SQL:\n{natural_query}"}
                ],
                tools=self._get_anthropic_tools_schema(),
                tool_choice={"type": "tool", "name": "generate_sql_query"}
            )
            
            # Extract tool call
            tool_call = response.content[0].tool_calls[0]
            result = tool_call.input
            # Add confidence score since it's expected in the existing code
            result['confidence'] = 0.9
        
        return result
    
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
