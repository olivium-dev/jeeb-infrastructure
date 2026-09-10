#!/usr/bin/env bash
# MSI one-time-password: default plan only; explicit preflight/deploy/verify use the shared engine.
set -euo pipefail
MSI_SERVICE_TOOL_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
exec python3 -I "$MSI_SERVICE_TOOL_DIR/msi_deploy.py" --service "one-time-password" "$@"
