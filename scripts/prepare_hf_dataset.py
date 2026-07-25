#!/usr/bin/env python3
"""Build and optionally push AryaYT/southwest-dqe-nl2sql.

Combines:
1. Hand-curated Southwest DQE / Kafka-S3-Glue-Redshift examples from this repo
2. A filtered slice of gretelai/synthetic_text_to_sql focused on analytics,
   window functions, joins, and CTEs useful for interview SQL practice
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from datasets import Dataset, DatasetDict, load_dataset


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "datasets" / "hf_southwest_dqe_nl2sql"
CURATED_FILES = [
    ROOT / "datasets" / "southwest_pipeline_nl2sql.jsonl",
    ROOT / "datasets" / "dqe_interview_examples.jsonl",
]

GRETEL_COMPLEXITY = {
    "window functions",
    "single join",
    "multiple_joins",
    "CTEs",
    "subqueries",
    "aggregation",
}
GRETEL_TASKS = {"analytics and reporting", "data retrieval"}
KEYWORD_RE = re.compile(
    r"\b(null|missing|duplicate|dedup|reconcil|lag|lead|row_number|rank|"
    r"dense_rank|outer join|partition|window|count\(|checksum|scd|"
    r"customer_id|order_id|event)\b",
    re.IGNORECASE,
)


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        rows.append(
            {
                "id": str(item.get("id") or f"curated-{len(rows)+1}"),
                "source": "arya-curated",
                "domain": item.get("domain", "data_quality"),
                "dialect": item.get("dialect", "sqlite"),
                "pipeline_stage": item.get("pipeline_stage", "interview"),
                "question": item.get("question") or item.get("sql_prompt"),
                "sql": item["sql"],
                "explanation": item.get("explanation") or item.get("sql_explanation", ""),
                "sql_context": item.get("sql_context", ""),
                "sql_complexity": item.get("sql_complexity", "curated"),
                "tags": ",".join(item.get("tags", [])) if isinstance(item.get("tags"), list) else str(item.get("tags", "")),
            }
        )
    return rows


def extract_gretel(limit: int) -> list[dict]:
    ds = load_dataset("gretelai/synthetic_text_to_sql", split="train")
    selected = []
    for row in ds:
        if row.get("sql_task_type") not in GRETEL_TASKS:
            continue
        if row.get("sql_complexity") not in GRETEL_COMPLEXITY:
            continue
        blob = " ".join(
            [
                str(row.get("sql_prompt", "")),
                str(row.get("sql", "")),
                str(row.get("sql_explanation", "")),
            ]
        )
        if not KEYWORD_RE.search(blob):
            continue
        selected.append(
            {
                "id": f"gretel-{row['id']}",
                "source": "gretelai/synthetic_text_to_sql",
                "domain": row.get("domain", "general"),
                "dialect": "ansi",
                "pipeline_stage": "interview_practice",
                "question": row["sql_prompt"],
                "sql": row["sql"],
                "explanation": row.get("sql_explanation", ""),
                "sql_context": row.get("sql_context", ""),
                "sql_complexity": row.get("sql_complexity", ""),
                "tags": row.get("sql_task_type", ""),
            }
        )
        if len(selected) >= limit:
            break
    return selected


def to_dataset(rows: list[dict]) -> DatasetDict:
    # Stable split: curated always in train; gretel 90/10.
    curated = [r for r in rows if r["source"] == "arya-curated"]
    gretel = [r for r in rows if r["source"] != "arya-curated"]
    split_at = max(1, int(len(gretel) * 0.9)) if gretel else 0
    train = curated + gretel[:split_at]
    test = gretel[split_at:] or curated[-max(1, len(curated) // 5) :]
    return DatasetDict(
        {
            "train": Dataset.from_list(train),
            "test": Dataset.from_list(test),
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gretel-limit", type=int, default=250)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--push", action="store_true", help="Push to Hugging Face Hub")
    parser.add_argument("--repo-id", default="AryaYT/southwest-dqe-nl2sql")
    parser.add_argument("--private", action="store_true")
    args = parser.parse_args()

    rows = []
    for path in CURATED_FILES:
        loaded = load_jsonl(path)
        print(f"Loaded {len(loaded)} curated rows from {path.name}")
        rows.extend(loaded)

    gretel_rows = extract_gretel(args.gretel_limit)
    print(f"Selected {len(gretel_rows)} gretel rows")
    rows.extend(gretel_rows)

    # Deduplicate by normalized question+sql
    seen = set()
    deduped = []
    for row in rows:
        key = (row["question"].strip().lower(), row["sql"].strip().lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)

    dataset = to_dataset(deduped)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    dataset.save_to_disk(str(args.out_dir))

    jsonl_path = ROOT / "datasets" / "southwest_dqe_nl2sql_train.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as fh:
        for row in dataset["train"]:
            fh.write(json.dumps(row, ensure_ascii=True) + "\n")

    print(f"Saved dataset to {args.out_dir}")
    print(f"Wrote train JSONL: {jsonl_path} ({len(dataset['train'])} rows)")
    print(f"Test rows: {len(dataset['test'])}")

    if args.push:
        dataset.push_to_hub(args.repo_id, private=args.private)
        print(f"Pushed to https://huggingface.co/datasets/{args.repo_id}")


if __name__ == "__main__":
    main()
