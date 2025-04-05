import sqlite3
from typing import Dict, List, Any, Optional, Tuple
import json

from models import SQLGenerationRequest, SQLGenerationResponse, SQLQueryResult, SQLAgentResponse
from llm_client import LLMClient

class SQLAgent:
    """Agent for handling natural language to SQL conversion and execution"""
    
    def __init__(self, db_path: str, llm_client: LLMClient, max_retries: int = 3):
        self.db_path = db_path
        self.llm_client = llm_client
        self.conn = None
        self.cursor = None
        self.max_retries = max_retries
        self._connect_to_db()
        self.schema_info = self._get_schema_info()
    
    def _connect_to_db(self) -> None:
        """Establish connection to the SQLite database"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row  # This enables column access by name
            self.cursor = self.conn.cursor()
        except sqlite3.Error as e:
            raise Exception(f"Database connection error: {str(e)}")
    
    def _get_schema_info(self) -> str:
        """Get the database schema information"""
        try:
            # Get table names
            self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in self.cursor.fetchall() if not row[0].startswith('sqlite_')]
            
            schema_info = "Database Schema:\n\n"
            
            for table in tables:
                schema_info += f"Table: {table}\n"
                
                # Get column information
                self.cursor.execute(f"PRAGMA table_info({table});")
                columns = self.cursor.fetchall()
                
                schema_info += "Columns:\n"
                for col in columns:
                    col_name = col['name']
                    col_type = col['type']
                    is_pk = "PRIMARY KEY" if col['pk'] == 1 else ""
                    schema_info += f"- {col_name} ({col_type}) {is_pk}\n"
                
                # Get sample data (first 3 rows)
                try:
                    self.cursor.execute(f"SELECT * FROM {table} LIMIT 3;")
                    rows = self.cursor.fetchall()
                    if rows:
                        schema_info += "Sample data:\n"
                        for row in rows:
                            row_dict = {k: row[k] for k in row.keys()}
                            schema_info += f"- {json.dumps(row_dict)}\n"
                except sqlite3.Error:
                    schema_info += "Could not retrieve sample data.\n"
                
                schema_info += "\n"
            
            return schema_info
        except sqlite3.Error as e:
            return f"Error retrieving schema: {str(e)}"
    
    def generate_sql(self, request: SQLGenerationRequest, error_message: str = None) -> SQLGenerationResponse:
        """Generate SQL from natural language query"""
        response = self.llm_client.generate_sql(request.query, self.schema_info, error_message)
        
        return SQLGenerationResponse(
            sql_query=response["sql_query"],
            explanation=response["explanation"]
        )
    
    def execute_sql(self, sql_query: str) -> Tuple[Optional[SQLQueryResult], Optional[str]]:
        """Execute a SQL query and return the results or error"""
        try:
            self.cursor.execute(sql_query)
            rows = self.cursor.fetchall()
            
            if not rows:
                return SQLQueryResult(columns=[], rows=[], row_count=0), None
            
            # Get column names
            columns = [desc[0] for desc in self.cursor.description]
            
            # Convert rows to lists
            row_data = [[row[col] for col in columns] for row in rows]
            
            result = SQLQueryResult(
                columns=columns,
                rows=row_data,
                row_count=len(row_data)
            )
            
            return result, None
        except sqlite3.Error as e:
            error_message = f"SQL execution error: {str(e)}"
            return None, error_message
    
    def improve_sql(self, natural_query: str, failed_sql: str, error_message: str) -> SQLGenerationResponse:
        """Improve a SQL query that failed with an error"""
        response = self.llm_client.improve_sql(natural_query, self.schema_info, failed_sql, error_message)
        
        return SQLGenerationResponse(
            sql_query=response["sql_query"],
            explanation=response["explanation"]
        )
    
    def process_query(self, natural_query: str) -> SQLAgentResponse:
        """Process a natural language query and return the complete response with retry logic"""
        request = SQLGenerationRequest(query=natural_query)
        
        # Initial SQL generation
        sql_response = self.generate_sql(request)
        current_sql = sql_response.sql_query
        current_explanation = sql_response.explanation
        
        # If no SQL was generated, return error
        if not current_sql:
            return SQLAgentResponse(
                natural_query=natural_query,
                generated_sql="",
                explanation=f"Failed to generate SQL: {current_explanation}",
                query_result=None,
                error="Could not generate SQL query"
            )
        
        # Try to execute the SQL with retries
        attempts = 0
        result = None
        error = None
        improvement_history = []
        
        while attempts < self.max_retries:
            result, error = self.execute_sql(current_sql)
            
            # If successful or no error, break the loop
            if not error:
                break
                
            # Record the improvement attempt
            improvement_history.append({
                "attempt": attempts + 1,
                "sql": current_sql,
                "error": error
            })
            
            # Try to improve the SQL
            improved_response = self.improve_sql(natural_query, current_sql, error)
            
            # If improvement failed or returned the same SQL, break the loop
            if not improved_response.sql_query or improved_response.sql_query == current_sql:
                break
                
            # Update current SQL and explanation for next attempt
            current_sql = improved_response.sql_query
            current_explanation += f"\n\nImproved SQL (attempt {attempts + 1}): {improved_response.explanation}"
            
            attempts += 1
        
        # Create the response
        return SQLAgentResponse(
            natural_query=natural_query,
            generated_sql=current_sql,
            explanation=current_explanation,
            query_result=result,
            error=error,
            improvement_history=improvement_history if improvement_history else None
        )
    
    def close(self) -> None:
        """Close the database connection"""
        if self.conn:
            self.conn.close()
