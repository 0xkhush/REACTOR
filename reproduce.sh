#!/usr/bin/env bash
# Root wrapper for scripts/reproduce.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$ROOT/scripts/reproduce.sh" "$@"
