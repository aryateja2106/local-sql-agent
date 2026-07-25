# Local SQL Agent

A Python SQL agent that turns natural language into SQL, executes it against a local SQLite practice database, and explains the result. It talks to any OpenAI-compatible local server (LM Studio or Ollama), so you can swap models without changing application code.

It is tuned for **Data Quality Engineer interview prep** around the Southwest-style pipeline:

`Kafka JSON → S3 Bronze (JSONL) → Glue/Spark → S3 Silver/Gold Parquet → Redshift COPY`

## Features

- Natural language → SQL through LM Studio / Ollama
- Automatic preference for stronger loaded models (Qwen3.6 35B, then Gemma 4 12B)
- Two practice databases:
  - `pipeline_database.db` — medallion / reconciliation / SCD drills
  - `sales_database.db` — original purchase/sales demo
- Streamlit UI with model picker, dialect toggle, and few-shot examples
- Read-only execution guard (`SELECT` / `WITH` / `EXPLAIN` only)
- Retry loop that asks the model to repair failed SQL
- Curated NL→SQL datasets for DQE interview patterns
- Hugging Face dataset: [`AryaYT/southwest-dqe-nl2sql`](https://huggingface.co/datasets/AryaYT/southwest-dqe-nl2sql)

## Project Structure

- `app.py` — Streamlit UI (pipeline + sales modes)
- `sql_agent.py` — generate / validate / execute / repair loop
- `llm_client.py` — OpenAI-compatible local client + few-shot selection
- `setup_pipeline_database.py` — Kafka→warehouse practice tables
- `setup_database.py` — original sales demo tables
- `datasets/southwest_pipeline_nl2sql.jsonl` — curated DQE/pipeline examples
- `datasets/dqe_interview_examples.jsonl` — shorter interview prompt set
- `scripts/prepare_hf_dataset.py` — merge curated + Gretel slice and push to HF
- `test_sql_safety.py` — offline read-only guard tests

## Prerequisites

- Python 3.9+
- [LM Studio](https://lmstudio.ai/) at `http://127.0.0.1:1234` **or** [Ollama](https://ollama.ai/)
- Recommended local models currently on this machine:
  - `unsloth/Qwen3.6-35B-A3B` (best SQL reasoning)
  - `lmstudio-community/gemma-4-12B-it-QAT` (strong mid-size fallback)

## Setup

```bash
git clone https://github.com/aryateja2106/local-sql-agent.git
cd local-sql-agent
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

python setup_pipeline_database.py
python setup_database.py
python add_user_purchase_data.py

cp .env.example .env
```

Load a model in LM Studio, then:

```bash
python run.py
# or
streamlit run app.py
```

## Interview-focused usage

1. In the sidebar, choose **Pipeline (Kafka→S3→Glue→Redshift)**
2. Keep dialect on **sqlite** to execute against the practice DB
3. Switch dialect to **redshift** when you want whiteboard-style `COPY` / `QUALIFY` answers without local execution
4. Keep **Use interview few-shot examples** enabled

### Example pipeline prompts

- Find the percentage of silver booking events with a missing customer ID
- Keep the newest bronze version of each event ID
- Find silver bookings missing from the Redshift fact table
- Reconcile source vs target orders (source-only / target-only / mismatch)
- Find staged customers that need a new SCD Type 2 version
- Balance Bronze accepted + quarantined counts against Silver

### Practice table map

| Table | Pipeline meaning |
| --- | --- |
| `bronze_events` | Raw Kafka landing + coordinates |
| `quarantine_events` | Rejected Bronze records |
| `silver_booking_events` | Clean, deduped events |
| `gold_daily_booking_metrics` | Business aggregates / DQ metrics |
| `redshift_fact_orders` | Warehouse fact after COPY |
| `source_orders` / `target_orders` | Reconciliation drills |
| `dim_customer` / `staged_customer` | SCD Type 2 drills |
| `batch_control` | Stage count balance |

## Dataset

Curated examples live in `datasets/`. To rebuild and push the Hugging Face dataset:

```bash
pip install datasets huggingface_hub
huggingface-cli login   # if needed
python scripts/prepare_hf_dataset.py --gretel-limit 250 --push --repo-id AryaYT/southwest-dqe-nl2sql
```

This merges:

1. Hand-written Southwest DQE / medallion SQL examples
2. A filtered slice of [`gretelai/synthetic_text_to_sql`](https://huggingface.co/datasets/gretelai/synthetic_text_to_sql) focused on joins, windows, CTEs, and analytics prompts useful for interview SQL

## Testing

```bash
python -m unittest test_sql_safety.py
python setup_pipeline_database.py
```

With a local model loaded:

```bash
python test_agent.py
```

## Environment Variables

| Variable | Purpose |
| --- | --- |
| `LLM_API_URL` | LM Studio (`http://127.0.0.1:1234`) or Ollama |
| `LLM_MODEL` | Optional explicit model id |
| `DATABASE_PATH` | Default DB path |
| `SQL_DIALECT` | `sqlite` or `redshift` |
| `SQL_AGENT_DOMAIN` | `pipeline` or `sales` |
| `SQL_AGENT_FEW_SHOT_PATH` | JSONL few-shot file |

## License

MIT — see `LICENSE`.
