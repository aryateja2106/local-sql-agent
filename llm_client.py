import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv


PREFERRED_MODEL_SUBSTRINGS = [
    "qwen3.6-35b",
    "qwen3.6",
    "gemma-4-12b",
    "gemma-4",
    "qwen3",
    "deepseek-r1",
]


class LLMClient:
    """Client for local models served through an OpenAI-compatible API."""

    def __init__(
        self,
        base_url: str = None,
        model_name: str = None,
        few_shot_path: str = None,
        dialect: str = "sqlite",
        domain: str = "sales",
    ):
        load_dotenv()

        self.base_url = (base_url or os.getenv("LLM_API_URL", "http://127.0.0.1:1234")).rstrip("/")
        self.chat_endpoint = f"{self.base_url}/v1/chat/completions"
        self.models_endpoint = f"{self.base_url}/v1/models"
        self.dialect = (dialect or os.getenv("SQL_DIALECT", "sqlite")).lower()
        self.domain = (domain or os.getenv("SQL_AGENT_DOMAIN", "sales")).lower()
        self.few_shot_examples = self._load_few_shot_examples(few_shot_path)
        configured = model_name or os.getenv("LLM_MODEL")
        self.model_name = configured or self.prefer_model(self.list_models()) or "qwen3.6-35b-a3b-ud-iq1_m"

    @staticmethod
    def prefer_model(model_ids: List[str]) -> Optional[str]:
        """Pick the strongest loaded local model for SQL generation."""
        if not model_ids:
            return None
        lowered = [(model_id, model_id.lower()) for model_id in model_ids]
        for needle in PREFERRED_MODEL_SUBSTRINGS:
            for model_id, low in lowered:
                if needle in low:
                    return model_id
        return model_ids[0]

    def list_models(self) -> List[str]:
        """Return locally loaded model IDs from LM Studio or Ollama's OpenAI API."""
        try:
            response = requests.get(self.models_endpoint, timeout=2)
            response.raise_for_status()
            return [item["id"] for item in response.json().get("data", []) if item.get("id")]
        except requests.exceptions.RequestException:
            return []

    def _load_few_shot_examples(self, few_shot_path: str) -> List[Dict[str, str]]:
        path = Path(few_shot_path or os.getenv("SQL_AGENT_FEW_SHOT_PATH", ""))
        if not path.is_file():
            return []

        examples = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            question = item.get("question") or item.get("sql_prompt")
            sql = item.get("sql")
            if not question or not sql:
                continue
            examples.append(
                {
                    "question": question,
                    "sql": sql,
                    "explanation": item.get("explanation") or item.get("sql_explanation") or "",
                    "dialect": (item.get("dialect") or "sqlite").lower(),
                    "pipeline_stage": item.get("pipeline_stage") or "",
                    "domain": item.get("domain") or "",
                }
            )
        return examples

    def _few_shot_context(self, query: str) -> str:
        """Select a small relevant subset so local models do not receive a huge prompt."""
        query_terms = set(re.findall(r"[a-z_]+", query.lower()))
        dialect_preferred = [
            example
            for example in self.few_shot_examples
            if example.get("dialect") in {self.dialect, "ansi", "sqlite"}
        ] or self.few_shot_examples

        ranked = sorted(
            dialect_preferred,
            key=lambda example: len(
                query_terms & set(re.findall(r"[a-z_]+", f"{example['question']} {example.get('pipeline_stage','')}".lower()))
            ),
            reverse=True,
        )[:2]
        if not ranked:
            return ""

        return "\n\n".join(
            "Practice example:\nQuestion: {question}\nSQL:\n{sql}\nWhy: {explanation}".format(**example)
            for example in ranked
        )

    @staticmethod
    def _strip_reasoning(content: str) -> str:
        """Remove common local-model reasoning wrappers before SQL extraction."""
        cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(r"<reasoning>.*?</reasoning>", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
        return cleaned.strip()

    def get_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> Dict[str, Any]:
        # Local reasoning models often spend hundreds of tokens in reasoning_content
        # before emitting the final answer; keep max_tokens high enough for both.
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            response = requests.post(self.chat_endpoint, json=payload, timeout=300)
            if not response.ok:
                detail = response.text[:500]
                raise Exception(
                    f"Error communicating with LLM API: {response.status_code} {response.reason}: {detail}"
                )
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"Error communicating with LLM API: {str(e)}")

    @staticmethod
    def _message_text(message: Dict[str, Any]) -> str:
        """Prefer final content; fall back to reasoning channels used by local models."""
        content = (message.get("content") or "").strip()
        if content:
            return content
        for key in ("reasoning_content", "reasoning", "thinking"):
            value = message.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _extract_sql_from_response(self, content: str) -> Dict[str, str]:
        content = self._strip_reasoning(content)

        if "```json" in content:
            try:
                json_content = content.split("```json")[1].split("```")[0].strip()
                result = json.loads(json_content)
                if "sql_query" in result:
                    return LLMClient._normalize_sql_result(
                        {
                            "sql_query": result.get("sql_query", ""),
                            "explanation": result.get("explanation", ""),
                        }
                    )
            except Exception:
                pass

        elif "```" in content:
            try:
                code_content = content.split("```")[1].split("```")[0].strip()
                if code_content.lower().startswith("sql"):
                    sql_query = code_content[3:].strip()
                else:
                    sql_query = code_content
                # If fenced block is JSON, parse it.
                if sql_query.lstrip().startswith("{"):
                    parsed = json.loads(sql_query)
                    if "sql_query" in parsed:
                        return LLMClient._normalize_sql_result(
                            {
                                "sql_query": parsed.get("sql_query", ""),
                                "explanation": parsed.get("explanation", ""),
                            }
                        )
                return LLMClient._normalize_sql_result(
                    {
                        "sql_query": sql_query,
                        "explanation": "Extracted SQL query from code block",
                    }
                )
            except Exception:
                pass

        try:
            start_idx = content.find("{")
            end_idx = content.rfind("}") + 1
            if start_idx >= 0 and end_idx > start_idx:
                result = json.loads(content[start_idx:end_idx])
                if "sql_query" in result:
                    return LLMClient._normalize_sql_result(
                        {
                            "sql_query": result.get("sql_query", ""),
                            "explanation": result.get("explanation", ""),
                        }
                    )
        except Exception:
            pass

        try:
            result = json.loads(content)
            if "sql_query" in result:
                return LLMClient._normalize_sql_result(
                    {
                        "sql_query": result.get("sql_query", ""),
                        "explanation": result.get("explanation", ""),
                    }
                )
        except Exception:
            pass

        if "SELECT" in content.upper() or "WITH" in content.upper() or "COPY" in content.upper():
            lines = content.split("\n")
            sql_lines = []
            capture = False
            for line in lines:
                upper = line.upper()
                if any(token in upper for token in ("SELECT", "WITH", "COPY", "UPDATE", "INSERT")) or capture:
                    capture = True
                    sql_lines.append(line)
                    if ";" in line:
                        break
            if sql_lines:
                sql_query = "\n".join(sql_lines).strip().rstrip(";")
                return self._normalize_sql_result(
                    {
                        "sql_query": sql_query,
                        "explanation": "Extracted SQL query from text",
                    }
                )

        return {
            "sql_query": "",
            "explanation": f"Error parsing LLM response: {content[:100]}...",
        }

    @staticmethod
    def _normalize_sql_result(result: Dict[str, str]) -> Dict[str, str]:
        sql = (result.get("sql_query") or "").strip()
        # Models sometimes emit a JSON fragment as the SQL field.
        if sql.startswith('"sql_query"') or sql.startswith("'sql_query'"):
            match = re.search(r'"sql_query"\s*:\s*"(.*?)"', sql, flags=re.DOTALL)
            if match:
                sql = match.group(1).encode("utf-8").decode("unicode_escape")
        sql = sql.strip().strip("`").strip()
        if sql.lower().startswith("sql"):
            sql = sql[3:].strip()
        result["sql_query"] = sql.rstrip(";").strip()
        return result

    def _domain_guidance(self) -> str:
        if self.domain == "pipeline":
            return """
        You are preparing SQL for a Data Quality Engineer interview around this pipeline:
        Kafka JSON events -> S3 Bronze (JSONL) -> Glue/Spark clean+dedupe -> S3 Silver/Gold Parquet -> Redshift COPY.

        Practice tables in this database:
        - bronze_events: raw Kafka landing with topic/partition/offset and malformed flags
        - quarantine_events: rejected Bronze records with reasons
        - silver_booking_events: validated, deduplicated booking events
        - gold_daily_booking_metrics: business aggregates and null percentages
        - redshift_fact_orders: warehouse fact table loaded from curated data
        - source_orders / target_orders: reconciliation drill tables
        - dim_customer / staged_customer: SCD Type 2 drills
        - batch_control: stage count balance checks
        - employees: ranking drills

        Prefer data-quality patterns:
        - NULL profiling with COUNT(*) - COUNT(col) and NULLIF
        - deterministic ROW_NUMBER dedup with ingestion_id / updated_at tiebreakers
        - left anti-joins and FULL OUTER JOIN reconciliation labels
        - SCD Type 2 current-row and hash-change detection
        - Bronze vs Silver vs Redshift count/value reconciliation
        """
        return """
        The database includes a user_purchase_behavior table that tracks:
        - Whether users have purchased products (has_purchased_product)
        - The likelihood of users purchasing products (purchase_likelihood)
        - Whether users have purchased services (has_purchased_service)
        - The likelihood of users purchasing services (service_purchase_likelihood)
        - The date of last interaction with the user (last_interaction_date)

        For purchase-behavior questions, JOIN user_purchase_behavior with customers for names.
        """

    def _dialect_rules(self) -> str:
        if self.dialect == "redshift":
            return """
        DIALECT: Amazon Redshift / ANSI warehouse SQL for interview whiteboard answers.
        - DATE_TRUNC, QUALIFY, COPY, and UPDATE...FROM are allowed when appropriate
        - Prefer fully qualified join columns
        - Never invent tables outside the provided schema unless the question is a COPY skeleton
        - Still return one statement focused on the interview ask
        - If returning COPY/DDL-style interview SQL, keep it minimal and explain assumptions
        """
        return """
        DIALECT: SQLite (must execute against the local practice database).
        - Use only tables/columns from the schema
        - Boolean flags are 0/1
        - Use single quotes for string literals
        - Prefer AS for aliases
        - Use FULL OUTER JOIN when needed (supported here)
        - Use IS / IS NOT for NULL-safe comparisons
        - Do not use DATE_TRUNC, QUALIFY, COPY, or Redshift-only syntax
        - For date bucketing use date() / strftime()
        - Generate a single read-only query: SELECT, WITH ... SELECT, or EXPLAIN QUERY PLAN
        - Never generate INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, ATTACH, or PRAGMA
        """

    def generate_sql(self, query: str, schema_info: str, error_message: str = None) -> Dict[str, str]:
        examples = self._few_shot_context(query)
        system_message = f"""You are an expert SQL agent that converts natural language into accurate SQL on the first attempt.

        Database schema:
        {schema_info}

        {self._domain_guidance()}
        {self._dialect_rules()}

        Task:
        1. Understand the natural language question
        2. Generate valid SQL for the selected dialect
        3. Briefly explain the data-quality or analytics intent

        {examples}

        Final answer requirements:
        - Put the final answer in normal assistant content, not only in hidden reasoning
        - Return ONLY a JSON object, no markdown fences
        {{
            "sql_query": "THE SQL QUERY",
            "explanation": "EXPLANATION OF THE QUERY"
        }}
        """

        user_message = query
        if error_message:
            user_message += (
                f"\n\nThe previous SQL query failed with the following error: {error_message}\n"
                "Please fix the SQL query and try again."
            )

        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ]

        try:
            response = self.get_completion(messages, temperature=0.1, max_tokens=2048)
            content = self._message_text(response["choices"][0]["message"])
            return self._extract_sql_from_response(content)
        except Exception as e:
            return {
                "sql_query": "",
                "explanation": f"Error generating SQL: {str(e)}",
            }

    def improve_sql(
        self,
        query: str,
        schema_info: str,
        original_sql: str,
        error_message: str,
    ) -> Dict[str, str]:
        system_message = f"""You are an expert SQL agent that fixes broken SQL queries.

        Database schema:
        {schema_info}

        {self._dialect_rules()}

        The user asked: "{query}"

        The following SQL query failed:
        ```sql
        {original_sql}
        ```

        Error message: {error_message}

        Fix the SQL for the selected dialect. Use only schema tables/columns.
        Return ONLY JSON:
        {{
            "sql_query": "THE FIXED SQL QUERY",
            "explanation": "EXPLANATION OF THE FIXES"
        }}
        """

        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": "Please fix the SQL query."},
        ]

        try:
            response = self.get_completion(messages, temperature=0.1, max_tokens=2048)
            content = self._message_text(response["choices"][0]["message"])
            return self._extract_sql_from_response(content)
        except Exception as e:
            return {
                "sql_query": "",
                "explanation": f"Error improving SQL: {str(e)}",
            }
