import json
import re
import sqlite3
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from models import SQLAgentResponse, SQLGenerationRequest, SQLGenerationResponse, SQLQueryResult

if TYPE_CHECKING:
    from llm_client import LLMClient


class SQLAgent:
    """Agent for handling natural language to SQL conversion and execution."""

    def __init__(self, db_path: str, llm_client: "LLMClient", max_retries: int = 3, execute_sql: bool = True):
        self.db_path = db_path
        self.llm_client = llm_client
        self.conn = None
        self.cursor = None
        self.max_retries = max_retries
        self.execute_sql_enabled = execute_sql
        self._connect_to_db()
        self.schema_info = self._get_schema_info()

    def _connect_to_db(self) -> None:
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row
            self.cursor = self.conn.cursor()
        except sqlite3.Error as e:
            raise Exception(f"Database connection error: {str(e)}")

    def _get_schema_info(self) -> str:
        try:
            self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in self.cursor.fetchall() if not row[0].startswith("sqlite_")]

            schema_info = "Database Schema:\n\n"
            for table in tables:
                schema_info += f"Table: {table}\n"
                self.cursor.execute(f"PRAGMA table_info({table});")
                columns = self.cursor.fetchall()
                schema_info += "Columns:\n"
                for col in columns:
                    col_name = col["name"]
                    col_type = col["type"]
                    is_pk = "PRIMARY KEY" if col["pk"] == 1 else ""
                    schema_info += f"- {col_name} ({col_type}) {is_pk}\n"

                try:
                    # Keep samples tiny so local reasoning models do not blow the context window.
                    self.cursor.execute(f"SELECT * FROM {table} LIMIT 1;")
                    rows = self.cursor.fetchall()
                    if rows:
                        schema_info += "Sample data:\n"
                        for row in rows:
                            row_dict = {}
                            for key in row.keys():
                                value = row[key]
                                if isinstance(value, str) and len(value) > 80:
                                    value = value[:77] + "..."
                                row_dict[key] = value
                            schema_info += f"- {json.dumps(row_dict, default=str)}\n"
                except sqlite3.Error:
                    schema_info += "Could not retrieve sample data.\n"
                schema_info += "\n"
            return schema_info
        except sqlite3.Error as e:
            return f"Error retrieving schema: {str(e)}"

    def generate_sql(self, request: SQLGenerationRequest, error_message: str = None) -> SQLGenerationResponse:
        response = self.llm_client.generate_sql(request.query, self.schema_info, error_message)
        return SQLGenerationResponse(
            sql_query=response["sql_query"],
            explanation=response["explanation"],
        )

    @staticmethod
    def is_read_only_sql(sql_query: str) -> bool:
        """Reject obvious write operations before an LLM-generated query reaches SQLite."""
        sql = re.sub(r"/\*.*?\*/|--[^\n]*", "", sql_query, flags=re.DOTALL).strip()
        sql = sql.rstrip(";").strip()
        if not sql or ";" in sql:
            return False

        first_word = re.match(r"[A-Za-z]+", sql)
        if not first_word or first_word.group(0).upper() not in {"SELECT", "WITH", "EXPLAIN"}:
            return False

        forbidden = re.compile(
            r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|ATTACH|DETACH|PRAGMA|VACUUM|COPY)\b",
            re.IGNORECASE,
        )
        return forbidden.search(sql) is None

    def execute_sql(self, sql_query: str) -> Tuple[Optional[SQLQueryResult], Optional[str]]:
        if not self.is_read_only_sql(sql_query):
            return None, "Only one read-only SELECT, WITH ... SELECT, or EXPLAIN SELECT query is allowed."
        try:
            self.cursor.execute(sql_query)
            rows = self.cursor.fetchall()

            if not rows:
                return SQLQueryResult(columns=[], rows=[], row_count=0), None

            columns = [desc[0] for desc in self.cursor.description]
            row_data = [[row[col] for col in columns] for row in rows]
            return SQLQueryResult(columns=columns, rows=row_data, row_count=len(row_data)), None
        except sqlite3.Error as e:
            return None, f"SQL execution error: {str(e)}"

    def improve_sql(self, natural_query: str, failed_sql: str, error_message: str) -> SQLGenerationResponse:
        response = self.llm_client.improve_sql(natural_query, self.schema_info, failed_sql, error_message)
        return SQLGenerationResponse(
            sql_query=response["sql_query"],
            explanation=response["explanation"],
        )

    def process_query(self, natural_query: str) -> SQLAgentResponse:
        request = SQLGenerationRequest(query=natural_query)
        sql_response = self.generate_sql(request)
        current_sql = sql_response.sql_query
        current_explanation = sql_response.explanation

        if not current_sql:
            return SQLAgentResponse(
                natural_query=natural_query,
                generated_sql="",
                explanation=f"Failed to generate SQL: {current_explanation}",
                query_result=None,
                error="Could not generate SQL query",
            )

        # Interview / Redshift whiteboard mode: generate only, do not force SQLite execution.
        if not self.execute_sql_enabled:
            return SQLAgentResponse(
                natural_query=natural_query,
                generated_sql=current_sql,
                explanation=current_explanation + "\n\nExecution skipped (interview dialect mode).",
                query_result=None,
                error=None,
            )

        attempts = 0
        result = None
        error = None
        improvement_history = []

        while attempts < self.max_retries:
            result, error = self.execute_sql(current_sql)
            if not error:
                break

            improvement_history.append(
                {
                    "attempt": attempts + 1,
                    "sql": current_sql,
                    "error": error,
                }
            )
            improved_response = self.improve_sql(natural_query, current_sql, error)
            if not improved_response.sql_query or improved_response.sql_query == current_sql:
                break

            current_sql = improved_response.sql_query
            current_explanation += f"\n\nImproved SQL (attempt {attempts + 1}): {improved_response.explanation}"
            attempts += 1

        return SQLAgentResponse(
            natural_query=natural_query,
            generated_sql=current_sql,
            explanation=current_explanation,
            query_result=result,
            error=error,
            improvement_history=improvement_history if improvement_history else None,
        )

    def close(self) -> None:
        if self.conn:
            self.conn.close()
