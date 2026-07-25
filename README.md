# Local SQL Agent

A **model-agnostic** Python SQL agent for Southwest-style **Data Quality Engineer** interview prep. It turns natural language into SQL, runs it against a local practice database, repairs failures, and lightly verifies results.

Works with any OpenAI-compatible local server (**LM Studio** or **Ollama**). On a 24GB Apple Silicon machine, the supported default is **Gemma 4 12B Instruct QAT**.

Canonical pipeline this project drills:

`Kafka JSON → S3 Bronze (JSONL) → Glue/Spark → S3 Silver/Gold Parquet → Redshift COPY`

## Recent updates

- **Gemma-first defaults** for 24GB unified memory. Qwen 3.6 35B is not auto-selected (it can pin ~12GB GPU/wired RAM and run very hot).
- **Agentic harness**: `generate → sanitize → execute → repair → verify` so noisy local-model output does not burn multiple slow retries.
- **SQL sanitization** strips markdown/JSON wrappers and keeps a single read-only statement; false “read-only” rejects that caused multi-minute queries are fixed.
- **Pipeline practice DB** (`setup_pipeline_database.py`) with Bronze/Silver/Gold, quarantine, reconciliation, SCD Type 2, and batch-control tables.
- **Curated NL→SQL dataset** plus Hugging Face export: [`AryaYT/southwest-dqe-nl2sql`](https://huggingface.co/datasets/AryaYT/southwest-dqe-nl2sql).
- **Cool-load helper** (`scripts/cool_load.sh`): Gemma, context 4096, `parallel=1`.
- **Accuracy eval** (`scripts/eval_accuracy.py`): scores by **result equivalence** against golden SQL, not exact string match.

## Features

- Natural language → SQL through LM Studio / Ollama (swap models without code changes)
- Streamlit UI: pipeline vs sales DB, model picker, sqlite vs redshift dialect, few-shot toggle
- Read-only execution guard (`SELECT` / `WITH` / `EXPLAIN`) with noisy-output sanitization
- Retry/repair loop only on real execution or safety failures
- Post-exec verification annotations (e.g. batch balance: accounted = silver + quarantine)
- Offline unit tests for the safety/sanitize path

## Project structure

| Path | Role |
| --- | --- |
| `app.py` | Streamlit UI |
| `sql_agent.py` | Sanitize / execute / repair / verify harness |
| `llm_client.py` | OpenAI-compatible client + few-shot selection |
| `setup_pipeline_database.py` | Kafka→warehouse practice tables |
| `setup_database.py` | Original sales demo tables |
| `datasets/southwest_pipeline_nl2sql.jsonl` | Curated DQE/pipeline examples |
| `datasets/dqe_interview_examples.jsonl` | Compact few-shot set |
| `scripts/cool_load.sh` | Safe Gemma load (low concurrency) |
| `scripts/eval_accuracy.py` | Result-equivalence accuracy harness |
| `scripts/prepare_hf_dataset.py` | Build/push HF dataset |
| `test_sql_safety.py` | Offline guard + sanitize tests |

## Prerequisites

- Python 3.9+
- [LM Studio](https://lmstudio.ai/) or [Ollama](https://ollama.ai/)
- Recommended model: `lmstudio-community/gemma-4-12B-it-QAT` (~7GB)
- Avoid keeping `Qwen3.6-35B` resident on 24GB machines

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

## Run (cool path)

Load one mid-size model, run **one query at a time**, then unload when finished:

```bash
./scripts/cool_load.sh          # gemma-4-12b-it-qat, context=4096, parallel=1
streamlit run app.py
# open http://127.0.0.1:8501

# when done:
lms unload --all && lms server stop
```

## Interview-focused usage

1. Sidebar → **Pipeline (Kafka→S3→Glue→Redshift)**
2. Dialect **sqlite** to execute locally; **redshift** for whiteboard-style SQL (no local exec)
3. Keep **Use interview few-shot examples** enabled

### Example prompts

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

## How the agentic harness works

```text
NL question
  → LLM generates SQL (model-agnostic OpenAI API)
  → sanitize (strip fences/JSON junk; keep one statement)
  → execute against SQLite (read-only guard)
  → on failure: ask model to repair with the error (limited retries)
  → on success: light verification annotations
```

Accuracy across the curated set:

```bash
./scripts/cool_load.sh
python scripts/eval_accuracy.py --limit 6 --model gemma-4-12b-it-qat
```

## Dataset

Curated examples live in `datasets/`. Rebuild/push the Hugging Face dataset:

```bash
pip install datasets huggingface_hub
huggingface-cli login   # if needed
python scripts/prepare_hf_dataset.py --gretel-limit 250 --push --repo-id AryaYT/southwest-dqe-nl2sql
```

Sources:

1. Hand-written Southwest DQE / medallion SQL examples
2. Filtered slice of [`gretelai/synthetic_text_to_sql`](https://huggingface.co/datasets/gretelai/synthetic_text_to_sql)

Published: https://huggingface.co/datasets/AryaYT/southwest-dqe-nl2sql

## Testing

```bash
python -m unittest test_sql_safety.py
python setup_pipeline_database.py
```

## Environment variables

| Variable | Purpose |
| --- | --- |
| `LLM_API_URL` | LM Studio (`http://127.0.0.1:1234`) or Ollama |
| `LLM_MODEL` | Prefer `gemma-4-12b-it-qat` |
| `DATABASE_PATH` | Default DB path |
| `SQL_DIALECT` | `sqlite` or `redshift` |
| `SQL_AGENT_DOMAIN` | `pipeline` or `sales` |
| `SQL_AGENT_FEW_SHOT_PATH` | JSONL few-shot file |

## Thermal notes (24GB Apple Silicon)

- Prefer Gemma QAT; do not leave Qwen 3.6 35B loaded.
- Use `./scripts/cool_load.sh` (`parallel=1`).
- Run one prompt at a time; unload with `lms unload --all && lms server stop` when idle.
- Fans are SMC-managed; userland tools cannot force them. Unloading the model is the fastest cool-down.

## License

MIT — see `LICENSE`.
