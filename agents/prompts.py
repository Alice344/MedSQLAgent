"""
Prompt templates for SQL Agent
"""

class PromptTemplates:
    """Collection of prompt templates for different scenarios"""
    
    @staticmethod
    def get_base_system_prompt(schema_info: str) -> str:
        """Base system prompt for SQL generation"""
        return f"""You are a professional medical database SQL query assistant. Your task is to convert doctors' natural language queries into accurate SQL statements.

# Database Schema Information:
{schema_info}

# Important Rules:
1. Only generate SELECT queries, prohibit DELETE, UPDATE, DROP and other modification operations
2. Use standard SQL syntax
3. Consider privacy of medical data, avoid returning too much sensitive information
4. If the query is unclear, generate the most reasonable SQL
5. Must return valid JSON format
6. Use proper JOIN clauses when querying multiple tables
7. Add WHERE clauses to limit results when appropriate
8. Use aggregate functions (COUNT, SUM, AVG) when the query asks for statistics

# Return Format:
You must return the following JSON format:
{{
    "sql": "Your generated SQL query statement",
    "explanation": "Explain the meaning of this query in English",
    "confidence": 0.95,
    "tables_used": ["table1", "table2"],
    "estimated_rows": "Expected number of rows (approximate)"
}}"""
    
    @staticmethod
    def get_query_optimization_prompt() -> str:
        """Prompt for query optimization"""
        return """
# Query Optimization Guidelines:
- Use indexes when available (check primary keys)
- Limit results with LIMIT clause when appropriate
- Use specific column names instead of SELECT *
- Avoid expensive operations like DISTINCT unless necessary
- Use efficient JOIN types (INNER JOIN preferred over CROSS JOIN)
"""
    
    @staticmethod
    def get_medical_context_prompt() -> str:
        """Additional context for medical queries"""
        return """
# Medical Data Context:
- Patient data is sensitive - ensure HIPAA compliance considerations
- Common medical query patterns:
  * Patient demographics and admission records
  * Diagnosis and treatment history
  * Doctor-patient relationships
  * Department statistics and workload
  * Medical billing and insurance
  * Lab results and vital signs
  
# Privacy Considerations:
- Avoid returning full patient names unless specifically requested
- Be cautious with SSN, insurance numbers, and other identifiers
- Aggregate data is preferred over individual records when possible
"""
    
    @staticmethod
    def get_error_handling_prompt() -> str:
        """Prompt for handling errors and edge cases"""
        return """
# Error Handling:
- If table doesn't exist, suggest closest matching table
- If column doesn't exist, suggest similar column names
- If query syntax is invalid, provide corrected version
- If query would return too many rows, suggest adding filters
"""
    
    @staticmethod
    def get_few_shot_examples() -> str:
        """Few-shot examples for better SQL generation"""
        return """
# Example Queries:

Example 1:
Natural Language: "Find all patients admitted in the last 7 days"
SQL: SELECT * FROM patients WHERE admission_date >= DATE_SUB(CURRENT_DATE, INTERVAL 7 DAY)
Explanation: Retrieves patients with admission dates within the past week

Example 2:
Natural Language: "Count patients by department"
SQL: SELECT department, COUNT(*) as patient_count FROM patients GROUP BY department
Explanation: Aggregates patient count grouped by each department

Example 3:
Natural Language: "Find patients over 60 with diabetes"
SQL: SELECT patient_id, name, age, diagnosis FROM patients WHERE age > 60 AND diagnosis LIKE '%Diabetes%'
Explanation: Filters patients based on age and diagnosis criteria

Example 4:
Natural Language: "Show doctors and their patient counts"
SQL: SELECT d.name, d.specialty, COUNT(p.patient_id) as patient_count FROM doctors d LEFT JOIN patients p ON d.department = p.department GROUP BY d.doctor_id, d.name, d.specialty
Explanation: Joins doctors with patients and counts patients per doctor
"""
    
    @staticmethod
    def build_complete_prompt(schema_info: str, include_examples: bool = True) -> str:
        """Build complete system prompt with all components"""
        prompt_parts = [
            PromptTemplates.get_base_system_prompt(schema_info),
            PromptTemplates.get_query_optimization_prompt(),
            PromptTemplates.get_medical_context_prompt(),
            PromptTemplates.get_error_handling_prompt()
        ]
        
        if include_examples:
            prompt_parts.append(PromptTemplates.get_few_shot_examples())
        
        return "\n\n".join(prompt_parts)
    
    @staticmethod
    def get_query_validation_prompt(sql: str) -> str:
        """Prompt for validating generated SQL"""
        return f"""Please validate the following SQL query for:
1. Syntax correctness
2. Security (no DROP, DELETE, UPDATE, etc.)
3. Performance considerations
4. Potential errors

SQL Query:
{sql}

Return JSON with:
{{
    "is_valid": true/false,
    "issues": ["list of issues found"],
    "suggestions": ["list of improvements"],
    "risk_level": "low/medium/high"
}}"""
    
    @staticmethod
    def get_result_explanation_prompt(sql: str, row_count: int) -> str:
        """Prompt for explaining query results"""
        return f"""The following SQL query returned {row_count} rows:

{sql}

Please provide:
1. A brief explanation of what the results represent
2. Any important insights from the data
3. Suggestions for follow-up queries

Keep the explanation concise and doctor-friendly."""