#!/usr/bin/env bash
set -euo pipefail
cd "${1:-.}"
python -m pip install -r requirements.txt
python -m pip install -e .
python -m autopilot_nodekit init --workspace . --manifest examples/manifest.yml --config examples/config.shell.yml --force
python -m autopilot_nodekit doctor --workspace .
