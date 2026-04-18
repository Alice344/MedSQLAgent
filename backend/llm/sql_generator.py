"""
LLM-based SQL query generator
"""
import os
import re
from typing import Optional
from openai import OpenAI
import logging

logger = logging.getLogger(__name__)

# Default model (override with OPENAI_MODEL in backend/.env)
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
EXPLAIN_MODEL = os.getenv("OPENAI_EXPLAIN_MODEL", "gpt-4o-mini")


class SQLGenerator:
    """Generates SQL queries from natural language using LLM"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAI API key is required. Set OPENAI_API_KEY in backend/.env "
                "or in your environment."
            )
        self.client = OpenAI(api_key=self.api_key)

    def generate_sql(
        self,
        natural_language_query: str,
        schema_description: str,
        model: Optional[str] = None,
    ) -> str:
        """Generate SQL query from natural language"""
        
        system_prompt = """You are an expert SQL developer specializing in Microsoft SQL Server (T-SQL).
Your task is to convert natural language queries into accurate, optimized SQL queries.

Rules:
1. Always use proper T-SQL syntax
2. CRITICAL: Use table and column names EXACTLY as they appear in the schema below — do NOT invent, shorten, or guess names
3. CRITICAL: Always qualify tables with their schema prefix exactly as shown (e.g. dbo.PatientDim, not caboodle.Patient or just Patient)
4. Include proper JOINs based on the foreign key relationships provided
5. Use appropriate WHERE clauses, aggregations, and ordering
6. Only return the SQL query, no explanations or markdown formatting
7. If the query is ambiguous, make reasonable assumptions using only tables present in the schema

Return ONLY the SQL query, nothing else."""

        user_prompt = f"""Database Schema (use ONLY these exact table and column names):
{schema_description}

User Request:
{natural_language_query}

Generate the SQL query using only the tables and columns listed above:"""

        model = model or DEFAULT_MODEL

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=1000,
            )

            raw = response.choices[0].message.content
            if raw is None or not str(raw).strip():
                raise ValueError("Model returned no SQL text; try again or check OPENAI_MODEL.")

            sql_query = str(raw).strip()

            # Remove markdown fences (```sql ... ```)
            fence = re.match(
                r"^\s*```(?:sql)?\s*\r?\n?(.*?)\r?\n?```\s*$",
                sql_query,
                re.DOTALL | re.IGNORECASE,
            )
            if fence:
                sql_query = fence.group(1).strip()
            else:
                if sql_query.startswith("```sql"):
                    sql_query = sql_query[6:]
                if sql_query.startswith("```"):
                    sql_query = sql_query[3:]
                if sql_query.endswith("```"):
                    sql_query = sql_query[:-3]
                sql_query = sql_query.strip()

            if not sql_query:
                raise ValueError("Model returned empty SQL after parsing.")

            return sql_query

        except Exception as e:
            logger.error(f"Error generating SQL: {e}")
            raise Exception(f"Failed to generate SQL query: {str(e)}") from e
    
    def explain_query(self, sql_query: str) -> str:
        """Explain what a SQL query does"""
        prompt = f"""Explain what this SQL query does in simple terms:
{sql_query}"""

        try:
            response = self.client.chat.completions.create(
                model=EXPLAIN_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=300,
            )
            text = response.choices[0].message.content
            return (text or "").strip() or "Unable to generate explanation"
        except Exception as e:
            logger.error(f"Error explaining query: {e}")
            return "Unable to generate explanation"



