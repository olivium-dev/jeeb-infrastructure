#!/usr/bin/env bash
# Offline planner only. Use an explicit per-service script for deployment.
set -euo pipefail
MSI_SERVICE_TOOL_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
exec python3 -I "$MSI_SERVICE_TOOL_DIR/plan_all.py" "$@"
