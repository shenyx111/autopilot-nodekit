#!/usr/bin/env bash
set -euo pipefail
WORKSPACE="${1:-.}"
WORKER_ID="${2:-local-worker}"
MAX_CYCLES="${3:-0}"
cd "$WORKSPACE"
python -m autopilot_nodekit worker-loop --workspace . --worker-id "$WORKER_ID" --max-cycles "$MAX_CYCLES"
