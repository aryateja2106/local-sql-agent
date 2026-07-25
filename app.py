import os
import subprocess
import sys
import traceback
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

from llm_client import LLMClient
from sql_agent import SQLAgent

st.set_page_config(page_title="Local SQL Agent · DQE Prep", layout="wide")

ROOT = Path(__file__).parent
SALES_DB = ROOT / "sales_database.db"
PIPELINE_DB = ROOT / "pipeline_database.db"
PIPELINE_EXAMPLES = ROOT / "datasets" / "southwest_pipeline_nl2sql.jsonl"
DQE_EXAMPLES = ROOT / "datasets" / "dqe_interview_examples.jsonl"

st.sidebar.title("SQL Agent")
st.sidebar.info(
    "Natural language → SQL against a local practice database, using LM Studio / Ollama. "
    "Use the Pipeline DB for Southwest DQE interview drills "
    "(Kafka → S3 Bronze → Glue → Parquet → Redshift). "
    "Default model on this machine: Gemma 4 12B QAT. Avoid Qwen 3.6 35B (too heavy for 24GB)."
)

db_choice = st.sidebar.selectbox(
    "Practice database",
    ["Pipeline (Kafka→S3→Glue→Redshift)", "Sales (original demo)"],
    index=0,
)
is_pipeline = db_choice.startswith("Pipeline")
db_path = PIPELINE_DB if is_pipeline else SALES_DB
domain = "pipeline" if is_pipeline else "sales"

if is_pipeline and not db_path.exists():
    st.sidebar.warning("Pipeline database not found. Creating it...")
    try:
        subprocess.run([sys.executable, str(ROOT / "setup_pipeline_database.py")], check=True)
        st.sidebar.success("Pipeline database ready.")
    except subprocess.CalledProcessError as e:
        st.sidebar.error(f"Failed to create pipeline database: {e}")

if not is_pipeline and not db_path.exists():
    st.sidebar.warning("Sales database not found. Creating it...")
    try:
        subprocess.run([sys.executable, str(ROOT / "setup_database.py")], check=True)
        st.sidebar.success("Sales database ready.")
    except subprocess.CalledProcessError as e:
        st.sidebar.error(f"Failed to create sales database: {e}")

dialect = st.sidebar.selectbox(
    "SQL dialect",
    ["sqlite", "redshift"],
    index=0,
    help="sqlite executes against the local DB. redshift is interview whiteboard mode (no local execution).",
)
execute_sql = dialect == "sqlite"

llm_url = st.sidebar.text_input("LLM API URL", value=os.getenv("LLM_API_URL", "http://127.0.0.1:1234"))
try:
    response = requests.get(f"{llm_url.rstrip('/')}/v1/models", timeout=2)
    if response.status_code == 200:
        st.sidebar.success("LLM endpoint is reachable")
    else:
        st.sidebar.error(f"LLM endpoint returned status code {response.status_code}")
except requests.exceptions.RequestException:
    st.sidebar.error("LLM endpoint is not reachable. Load a model in LM Studio first.")

default_examples = PIPELINE_EXAMPLES if is_pipeline else DQE_EXAMPLES
use_examples = st.sidebar.checkbox(
    "Use interview few-shot examples",
    value=is_pipeline,
    help=f"Loads examples from {default_examples.name}",
)

try:
    llm_client = LLMClient(
        base_url=llm_url,
        few_shot_path=str(default_examples) if use_examples and default_examples.exists() else None,
        dialect=dialect,
        domain=domain,
    )
    available_models = llm_client.list_models()
    if available_models:
        preferred = LLMClient.prefer_model(available_models) or llm_client.model_name
        if llm_client.model_name in available_models:
            default_index = available_models.index(llm_client.model_name)
        elif preferred in available_models:
            default_index = available_models.index(preferred)
        else:
            default_index = 0
        llm_client.model_name = st.sidebar.selectbox("Loaded local model", available_models, index=default_index)
        if "qwen3.6" in llm_client.model_name.lower() or "35b" in llm_client.model_name.lower():
            st.sidebar.warning(
                "This model is too heavy for the 24GB profile. Prefer gemma-4-12b-it-qat "
                "and unload Qwen when idle."
            )
    else:
        llm_client.model_name = st.sidebar.text_input("Model ID", value=llm_client.model_name)

    st.sidebar.caption("Thermal tip: one query at a time. Unload the model when finished.")

    sql_agent = SQLAgent(str(db_path), llm_client, max_retries=2, execute_sql=execute_sql)
except Exception as e:
    st.error(f"Error initializing SQL Agent: {str(e)}")
    st.stop()

st.title("Local SQL Agent")
if is_pipeline:
    st.subheader("Southwest DQE pipeline practice")
    st.caption(
        "Canonical path: Kafka JSON → S3 Bronze JSONL → Glue/Spark → Silver/Gold Parquet → Redshift COPY. "
        "Ask validation, dedup, SCD, and reconciliation questions."
    )
    examples = [
        "Find the percentage of silver booking events with a missing customer ID.",
        "Keep the newest bronze version of each event ID using ingestion_id as the tiebreaker.",
        "Find silver bookings that did not land in the Redshift fact table.",
        "Reconcile source and target orders and label source-only, target-only, matched, and amount mismatches.",
        "Find staged customers that would create a new SCD Type 2 version because the row hash changed.",
        "Compare bronze accepted rows plus quarantined rows against silver row counts for the latest batch.",
    ]
else:
    st.subheader("Ask questions about the sales database in natural language")
    examples = [
        "Show me the top 5 customers by total order amount",
        "What are the most popular products in the Electronics category?",
        "How many orders were placed in the last 6 months?",
        "Which customers have not placed any orders?",
        "What is the average order value by product category?",
    ]

st.caption("Example queries:")
cols = st.columns(2)
for idx, ex in enumerate(examples):
    if cols[idx % 2].button(ex, use_container_width=True):
        st.session_state.query = ex

query = st.text_area("Enter your query:", height=100, key="query")

if st.button("Run Query", type="primary"):
    if not query:
        st.warning("Please enter a query.")
    else:
        with st.spinner("Processing query..."):
            try:
                response = sql_agent.process_query(query)

                st.subheader("Generated SQL")
                st.code(response.generated_sql, language="sql")

                st.subheader("Explanation")
                st.write(response.explanation)

                if response.improvement_history:
                    with st.expander(f"Retry / repair history ({len(response.improvement_history)} attempts)"):
                        st.json(response.improvement_history)
                        st.caption(
                            "Harness flow: generate → sanitize → execute → repair on SQLite/safety errors. "
                            "Fewer repairs usually means cleaner first-pass SQL."
                        )

                if dialect == "redshift":
                    st.info("Redshift interview mode: SQL was generated for whiteboard practice and not executed locally.")
                elif response.error:
                    st.error(f"Error executing SQL: {response.error}")
                elif response.query_result is not None:
                    st.subheader("Results")
                    if response.query_result.row_count == 0:
                        st.info("Query returned no results.")
                    else:
                        df = pd.DataFrame(
                            response.query_result.rows,
                            columns=response.query_result.columns,
                        )
                        st.dataframe(df, use_container_width=True)
                        st.caption(f"Returned {response.query_result.row_count} rows")
                        if "Verification:" in (response.explanation or ""):
                            st.success("Post-exec verification annotations were added to the explanation.")
                        st.download_button(
                            label="Download results as CSV",
                            data=df.to_csv(index=False),
                            file_name="query_results.csv",
                            mime="text/csv",
                        )
            except Exception as e:
                st.error(f"Error processing query: {str(e)}")
                st.error(traceback.format_exc())

with st.expander("View Database Schema"):
    st.code(sql_agent.schema_info)

st.sidebar.markdown("---")
st.sidebar.caption(f"Model: `{llm_client.model_name}` · Dialect: `{dialect}` · Domain: `{domain}`")
