#!/usr/bin/env bash
set -euo pipefail

# Convenience wrapper around oracle.py
# Usage:
#   scripts/oracle.sh --task "..." --entry "path::reason" ...

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "${SCRIPT_DIR}/oracle.py" "$@"
