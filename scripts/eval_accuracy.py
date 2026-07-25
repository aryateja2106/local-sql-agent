#!/usr/bin/env python3
"""Model-agnostic accuracy harness for the local SQL agent.

For each curated sqlite example:
1. Ask the configured local model to generate SQL from the question
2. Sanitize + execute against pipeline_database.db
3. Compare result rows against the golden SQL result (execution equivalence)

This validates behavior, not exact SQL string match, so alternate correct SQL passes.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def normalize_rows(columns, rows):
    colmap = {c.lower(): i for i, c in enumerate(columns)}
    # Sort columns for stable compare when aliases differ but values match poorly;
    # instead compare as sorted tuples of values when column counts match.
    normalized = []
    for row in rows:
        normalized.append(tuple("" if v is None else v for v in row))
    return sorted(normalized)


def run_sql(conn: sqlite3.Connection, sql: str):
    cur = conn.execute(sql)
    rows = cur.fetchall()
    columns = [d[0] for d in cur.description] if cur.description else []
    return columns, [list(r) for r in rows]


def load_examples(path: Path):
    examples = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if item.get("dialect", "sqlite") != "sqlite":
            continue
        examples.append(item)
    return examples


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--examples",
        type=Path,
        default=ROOT / "datasets" / "southwest_pipeline_nl2sql.jsonl",
    )
    parser.add_argument("--db", type=Path, default=ROOT / "pipeline_database.db")
    parser.add_argument("--model", default=None, help="Override LLM model id")
    parser.add_argument("--limit", type=int, default=6, help="Max examples to evaluate")
    parser.add_argument("--sleep", type=float, default=0.5, help="Pause between calls to reduce heat")
    args = parser.parse_args()

    import sys

    sys.path.insert(0, str(ROOT))
    from llm_client import LLMClient
    from sql_agent import SQLAgent

    if not args.db.exists():
        raise SystemExit(f"Missing DB {args.db}. Run setup_pipeline_database.py first.")

    examples = load_examples(args.examples)[: args.limit]
    client = LLMClient(
        few_shot_path=str(ROOT / "datasets" / "southwest_pipeline_nl2sql.jsonl"),
        dialect="sqlite",
        domain="pipeline",
        model_name=args.model,
    )
    if args.model:
        client.model_name = args.model
    else:
        preferred = LLMClient.prefer_model(client.list_models())
        if preferred:
            client.model_name = preferred

    print(f"Model: {client.model_name}")
    print(f"Examples: {len(examples)}")

    agent = SQLAgent(str(args.db), client, max_retries=2, execute_sql=True)
    gold_conn = sqlite3.connect(args.db)

    passed = 0
    results = []
    try:
        for idx, example in enumerate(examples, 1):
            question = example["question"]
            gold_sql = example["sql"]
            t0 = time.time()
            response = agent.process_query(question)
            elapsed = time.time() - t0

            ok = False
            detail = ""
            if response.error or not response.generated_sql:
                detail = response.error or "empty sql"
            else:
                try:
                    g_cols, g_rows = run_sql(gold_conn, gold_sql)
                    # Compare against executed agent result
                    a_cols = response.query_result.columns if response.query_result else []
                    a_rows = response.query_result.rows if response.query_result else []
                    # Value-multiset compare (order-insensitive) when shapes match.
                    if len(a_cols) == len(g_cols) and normalize_rows(a_cols, a_rows) == normalize_rows(
                        g_cols, g_rows
                    ):
                        ok = True
                        detail = "result_match"
                    elif response.query_result and response.query_result.row_count == len(g_rows):
                        # Soft pass: same cardinality, useful signal for interview drills.
                        ok = False
                        detail = f"row_count_only_match ({len(g_rows)})"
                    else:
                        detail = (
                            f"result_mismatch agent_rows={len(a_rows)} gold_rows={len(g_rows)} "
                            f"agent_cols={a_cols} gold_cols={g_cols}"
                        )
                except Exception as exc:
                    detail = f"gold_exec_error: {exc}"

            passed += int(ok)
            status = "PASS" if ok else "FAIL"
            print(f"[{idx}/{len(examples)}] {status} {elapsed:.1f}s :: {question[:70]}")
            print(f"  sql: {response.generated_sql}")
            print(f"  detail: {detail}")
            if response.improvement_history:
                print(f"  repairs: {len(response.improvement_history)}")
            results.append(
                {
                    "id": example.get("id"),
                    "ok": ok,
                    "seconds": round(elapsed, 2),
                    "question": question,
                    "generated_sql": response.generated_sql,
                    "detail": detail,
                    "repairs": len(response.improvement_history or []),
                }
            )
            time.sleep(args.sleep)
    finally:
        agent.close()
        gold_conn.close()

    out = ROOT / "datasets" / "eval_last_run.json"
    out.write_text(json.dumps({"model": client.model_name, "results": results}, indent=2), encoding="utf-8")
    print(f"\nSUMMARY {passed}/{len(examples)} exact-result passes")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
