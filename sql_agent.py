import json
import re
import sqlite3
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from models import SQLAgentResponse, SQLGenerationRequest, SQLGenerationResponse, SQLQueryResult

if TYPE_CHECKING:
    from llm_client import LLMClient


FORBIDDEN_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|ATTACH|DETACH|PRAGMA|VACUUM|COPY|GRANT|REVOKE)\b",
    re.IGNORECASE,
)


class SQLAgent:
    """Model-agnostic NL→SQL agent with sanitize → execute → repair harness."""

    def __init__(
        self,
        db_path: str,
        llm_client: "LLMClient",
        max_retries: int = 2,
        execute_sql: bool = True,
    ):
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
        sql = self.sanitize_sql(response.get("sql_query", ""))
        return SQLGenerationResponse(
            sql_query=sql,
            explanation=response.get("explanation", ""),
        )

    @staticmethod
    def _split_first_statement(sql: str) -> Tuple[str, str]:
        """Return (first_statement, remainder) splitting on the first top-level semicolon."""
        in_single = False
        in_double = False
        for idx, ch in enumerate(sql):
            if ch == "'" and not in_double:
                in_single = not in_single
            elif ch == '"' and not in_single:
                in_double = not in_double
            elif ch == ";" and not in_single and not in_double:
                return sql[:idx].strip(), sql[idx + 1 :].strip()
        return sql.strip(), ""

    @classmethod
    def sanitize_sql(cls, sql_query: str) -> str:
        """Pull a single executable read-oriented statement out of noisy model output."""
        if not sql_query:
            return ""

        sql = sql_query.strip()

        # Recover JSON field before stripping quotes from the whole blob.
        if re.search(r'"sql_query"\s*:', sql, flags=re.IGNORECASE):
            match = re.search(r'"sql_query"\s*:\s*"(.*?)"\s*(,|})', sql, flags=re.DOTALL | re.IGNORECASE)
            if match:
                sql = match.group(1).encode("utf-8").decode("unicode_escape").strip()

        sql = sql.replace("```sql", "```").replace("```SQL", "```")
        if "```" in sql:
            parts = sql.split("```")
            if len(parts) >= 2 and parts[1].strip():
                sql = parts[1].strip()

        sql = re.sub(r"^(sql_query|sql)\s*[:=]\s*", "", sql, flags=re.IGNORECASE).strip()
        sql = sql.strip().strip("`").strip()
        if (sql.startswith('"') and sql.endswith('"')) or (sql.startswith("'") and sql.endswith("'")):
            sql = sql[1:-1].strip()

        start = re.search(r"\b(WITH|SELECT|EXPLAIN)\b", sql, flags=re.IGNORECASE)
        if not start:
            return ""
        sql = sql[start.start() :].strip()
        first, _remainder = cls._split_first_statement(sql)
        return first

    @classmethod
    def read_only_rejection_reason(cls, sql_query: str) -> Optional[str]:
        original = sql_query or ""
        # Prefer fenced SQL when present so trailing prose cannot false-reject.
        probe = original
        if "```" in original:
            parts = original.replace("```sql", "```").replace("```SQL", "```").split("```")
            if len(parts) >= 2 and parts[1].strip():
                probe = parts[1].strip()

        start = re.search(r"\b(WITH|SELECT|EXPLAIN)\b", probe, flags=re.IGNORECASE)
        if start:
            _first, remainder = cls._split_first_statement(probe[start.start() :])
            if remainder and FORBIDDEN_SQL.search(remainder):
                return "Multiple statements detected; trailing write/DDL is not allowed."

        sql = cls.sanitize_sql(sql_query)
        if not sql:
            return "Could not extract a SELECT/WITH/EXPLAIN statement from the model output."

        first_word = re.match(r"[A-Za-z]+", sql)
        if not first_word or first_word.group(0).upper() not in {"SELECT", "WITH", "EXPLAIN"}:
            return f"Query must start with SELECT/WITH/EXPLAIN (got {first_word.group(0) if first_word else 'empty'})."

        forbidden = FORBIDDEN_SQL.search(sql)
        if forbidden:
            return f"Forbidden keyword in query: {forbidden.group(1).upper()}."
        return None

    @classmethod
    def is_read_only_sql(cls, sql_query: str) -> bool:
        return cls.read_only_rejection_reason(sql_query) is None

    def execute_sql(self, sql_query: str) -> Tuple[Optional[SQLQueryResult], Optional[str]]:
        # Reject on the raw payload first so trailing DROP/INSERT after a SELECT cannot pass.
        reason = self.read_only_rejection_reason(sql_query)
        if reason:
            return None, f"Only one read-only SELECT, WITH ... SELECT, or EXPLAIN SELECT query is allowed. ({reason})"
        sql = self.sanitize_sql(sql_query)
        try:
            self.cursor.execute(sql)
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
            sql_query=self.sanitize_sql(response.get("sql_query", "")),
            explanation=response.get("explanation", ""),
        )

    def verify_result(
        self,
        natural_query: str,
        result: SQLQueryResult,
    ) -> Optional[Dict[str, Any]]:
        """Lightweight post-exec checks. Golden checks live in scripts/eval_accuracy.py."""
        checks = []
        if result.row_count > 0 and not result.columns:
            checks.append("missing_columns")

        q = natural_query.lower()
        if "bronze" in q and "quarantine" in q and "silver" in q and result.row_count == 1:
            cols = {c.lower(): idx for idx, c in enumerate(result.columns)}
            row = result.rows[0]
            if "accounted_rows" in cols and "silver_rows" in cols and "quarantine_count" in cols:
                accounted = row[cols["accounted_rows"]]
                silver = row[cols["silver_rows"]]
                quarantine = row[cols["quarantine_count"]]
                if accounted == silver + quarantine:
                    checks.append("accounted_rows_ok")
                else:
                    checks.append("accounted_rows_mismatch")
            elif "bronze_plus_quarantine" in cols and "silver_count" in cols:
                checks.append("batch_balance_shape_ok")
        return {"checks": checks} if checks else None

    def process_query(self, natural_query: str) -> SQLAgentResponse:
        """Agentic loop: generate → sanitize → execute → repair on real failures."""
        request = SQLGenerationRequest(query=natural_query)
        sql_response = self.generate_sql(request)
        current_sql = self.sanitize_sql(sql_response.sql_query)
        current_explanation = sql_response.explanation

        if not current_sql:
            return SQLAgentResponse(
                natural_query=natural_query,
                generated_sql="",
                explanation=f"Failed to generate SQL: {current_explanation}",
                query_result=None,
                error="Could not generate SQL query",
            )

        if not self.execute_sql_enabled:
            return SQLAgentResponse(
                natural_query=natural_query,
                generated_sql=current_sql,
                explanation=current_explanation + "\n\nExecution skipped (interview dialect mode).",
                query_result=None,
                error=None,
            )

        improvement_history = []
        result = None
        error = None

        for attempt in range(self.max_retries + 1):
            result, error = self.execute_sql(current_sql)
            if not error:
                verification = self.verify_result(natural_query, result)
                if verification and verification.get("checks"):
                    current_explanation += f"\n\nVerification: {', '.join(verification['checks'])}"
                break

            improvement_history.append(
                {
                    "attempt": attempt + 1,
                    "sql": current_sql,
                    "error": error,
                }
            )
            if attempt >= self.max_retries:
                break

            improved_response = self.improve_sql(natural_query, current_sql, error)
            improved_sql = self.sanitize_sql(improved_response.sql_query)
            if not improved_sql or improved_sql == current_sql:
                break

            current_sql = improved_sql
            current_explanation += (
                f"\n\nImproved SQL (attempt {attempt + 1}): {improved_response.explanation}"
            )

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
