from typing import Dict, Any, Optional
import json
import requests
from openai import OpenAI
from anthropic import Anthropic
from config.database import DatabaseConfig
from utils.db_connector import DatabaseConnector
from utils.schema_vector_store import SchemaVectorStore
import pandas as pd

class SQLAgent:
    """Natural language to SQL Agent"""
    
    def __init__(self, db: Optional[DatabaseConnector] = None, 
                 vector_store: Optional[SchemaVectorStore] = None,
                 use_vector_search: bool = True):
        """
        Initialize SQL Agent
        
        Args:
            db: DatabaseConnector instance (if None, creates new one)
            vector_store: SchemaVectorStore instance (if None, creates new one)
            use_vector_search: Whether to use vector search for schema retrieval
        """
        self.db = db if db else DatabaseConnector()
        self.provider = DatabaseConfig.LLM_PROVIDER
        self.use_vector_search = use_vector_search
        
        # Initialize LLM client
        if self.provider == 'openai':
            self.client = OpenAI(api_key=DatabaseConfig.OPENAI_API_KEY)
            self.model = DatabaseConfig.MODEL_NAME
        elif self.provider == 'claude':
            self.client = Anthropic(api_key=DatabaseConfig.ANTHROPIC_API_KEY)
            self.model = 'claude-sonnet-4-5-20250929'
        elif self.provider == 'ollama':
            self.model = DatabaseConfig.MODEL_NAME  # e.g., 'llama3' or 'mistral'
        
        # Initialize vector store
        self.vector_store = vector_store
        if self.vector_store is None:
            self.vector_store = SchemaVectorStore()
        
        # Get database schemas
        self.schemas = self.db.get_all_schemas()
        
        # If vector store is empty, populate it with current schemas
        if len(self.vector_store.metadata) == 0 and self.schemas:
            self.vector_store.add_schemas(self.schemas)
    
    def refresh_schemas(self):
        """Refresh schemas from database and update vector store"""
        self.schemas = self.db.get_all_schemas()
        if self.schemas:
            self.vector_store.clear()
            self.vector_store.add_schemas(self.schemas)
    
    def _build_system_prompt(self, natural_query: Optional[str] = None) -> str:
        """Build system prompt with relevant schemas"""
        if self.use_vector_search and natural_query and self.vector_store:
            # Use vector search to find relevant schemas
            relevant_schemas = self.vector_store.search(natural_query, top_k=10)
            if relevant_schemas:
                # Use only relevant schemas
                schemas_dict = {item['table_name']: item['schema'] for item in relevant_schemas}
                schema_text = self._format_schemas(schemas_dict)
            else:
                # Fallback to all schemas
                schema_text = self._format_schemas()
        else:
            # Use all schemas
            schema_text = self._format_schemas()
        
        return f"""You are a professional medical database SQL query assistant. Your task is to convert doctors' natural language queries into accurate SQL statements.

# Database Schema Information:
{schema_text}

# Important Rules:
1. Only generate SELECT queries, prohibit DELETE, UPDATE, DROP and other modification operations
2. Use standard SQL syntax
3. Consider privacy of medical data, avoid returning too much sensitive information
4. If the query is unclear, generate the most reasonable SQL
5. Must return valid JSON format

# Return Format:
You must return the following JSON format:
{{
    "sql": "Your generated SQL query statement",
    "explanation": "Explain the meaning of this query in English",
    "confidence": 0.95,
    "tables_used": ["table1", "table2"]
}}"""
    
    def _format_schemas(self, schemas: Optional[Dict[str, Dict]] = None) -> str:
        """Format database schema information"""
        if schemas is None:
            schemas = self.schemas
        
        schema_lines = []
        for table_name, schema in schemas.items():
            schema_lines.append(f"\nTable: {table_name}")
            schema_lines.append("Columns:")
            for col in schema['columns']:
                nullable = "Nullable" if col['nullable'] else "Not Null"
                schema_lines.append(f"  - {col['name']} ({col['type']}, {nullable})")
            if schema.get('primary_key'):
                schema_lines.append(f"  Primary Key: {', '.join(schema['primary_key'])}")
        
        return '\n'.join(schema_lines)
    
    def generate_sql(self, natural_query: str) -> Dict[str, Any]:
        """Generate SQL from natural language"""
        
        system_prompt = self._build_system_prompt(natural_query)
        
        if self.provider == 'openai':
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Please convert the following query to SQL:\n{natural_query}"}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            result = json.loads(response.choices[0].message.content)
        
        elif self.provider == 'claude':
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": f"Please convert the following query to SQL:\n{natural_query}"}
                ],
                temperature=0.1
            )
            # Claude returns text, need to extract JSON
            content = response.content[0].text
            # Try to extract JSON
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                result = json.loads(content)
        
        elif self.provider == 'ollama':
            # Call Ollama API
            try:
                response = requests.post(
                    f"{DatabaseConfig.OLLAMA_BASE_URL}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": f"System: {system_prompt}\n\nUser: Please convert the following query to SQL:\n{natural_query}",
                        "stream": False,
                        "temperature": 0.1,
                        "format": "json"
                    }
                )
                response.raise_for_status()
                response_data = response.json()
                
                # Extract the generated content from 'generate' API response
                content = response_data.get("response", "")
                
                # Try to extract JSON from the content
                try:
                    result = json.loads(content)
                except json.JSONDecodeError:
                    # If the model didn't return proper JSON, try to extract it
                    import re
                    json_match = re.search(r'\{.*\}', content, re.DOTALL)
                    if json_match:
                        result = json.loads(json_match.group())
                    else:
                        # Fallback to a basic structure
                        result = {
                            "sql": content.strip(),
                            "explanation": "SQL query generated by Ollama",
                            "confidence": 0.7,
                            "tables_used": []
                        }
            except Exception as e:
                result = {
                    "sql": "SELECT 'Error generating SQL' AS error_message",
                    "explanation": f"Failed to generate SQL: {str(e)}",
                    "confidence": 0,
                    "tables_used": []
                }
        
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