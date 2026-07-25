# NL→SQL datasets for Southwest DQE prep

| File | Purpose |
| --- | --- |
| `southwest_pipeline_nl2sql.jsonl` | Hand-curated Kafka→S3→Glue→Redshift practice prompts (executable SQLite + Redshift interview SQL) |
| `dqe_interview_examples.jsonl` | Compact few-shot set for the Streamlit agent |
| `southwest_dqe_nl2sql_train.jsonl` | Combined train export (curated + filtered Gretel slice) |

Published Hugging Face dataset:

https://huggingface.co/datasets/AryaYT/southwest-dqe-nl2sql

Rebuild / push:

```bash
python scripts/prepare_hf_dataset.py --gretel-limit 250 --push --repo-id AryaYT/southwest-dqe-nl2sql
```
