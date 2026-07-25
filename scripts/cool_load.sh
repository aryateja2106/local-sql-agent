#!/usr/bin/env bash
# Cool/safe LM Studio load for this 24GB M4 Pro machine.
# Default: Gemma 4 12B QAT only. Do not load Qwen 3.6 35B here.
set -euo pipefail

LMS="${LMS:-$HOME/.lmstudio/bin/lms}"
MODEL="${1:-gemma-4-12b-it-qat}"
CONTEXT="${CONTEXT:-4096}"
PARALLEL="${PARALLEL:-1}"

if [[ "$MODEL" == *qwen3.6* || "$MODEL" == *35b* ]]; then
  echo "Refusing to cool-load '$MODEL' on this machine profile." >&2
  echo "Use Gemma instead: $0 gemma-4-12b-it-qat" >&2
  exit 1
fi

if [[ ! -x "$LMS" ]]; then
  echo "lms not found at $LMS" >&2
  exit 1
fi

echo "Unloading any resident models..."
"$LMS" unload --all >/dev/null 2>&1 || true

echo "Starting server (if needed)..."
"$LMS" server start >/dev/null 2>&1 || true

echo "Loading $MODEL (context=$CONTEXT parallel=$PARALLEL)..."
"$LMS" load "$MODEL" -y -c "$CONTEXT" --parallel "$PARALLEL"

echo
"$LMS" status
"$LMS" ps
echo
echo "Cool mode ready. Run ONE query at a time."
echo "When done: $LMS unload --all && $LMS server stop"
