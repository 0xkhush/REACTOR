#!/usr/bin/env bash
# Prerequisites: Python 3.10–3.12, git, ffmpeg; external .env.local and released audio.
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
PYTHON="${PYTHON:-python3}"
VENV="${REACTOR_VENV:-$ROOT/.venv}"
"$PYTHON" -c 'import sys; assert (3,10) <= sys.version_info[:2] <= (3,12), "Use Python 3.10–3.12"'
command -v ffmpeg >/dev/null || { printf '%s\n' 'Install ffmpeg before reproduction.' >&2; exit 1; }
test -f "$ROOT/.env.local" || { printf '%s\n' 'Copy .env.example to .env.local and configure credentials/model.' >&2; exit 1; }
if [[ ! -x "$VENV/bin/python" ]]; then
  "$PYTHON" -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install -e "$ROOT[dev,voice]"
mkdir -p "$ROOT/vendor"
"$VENV/bin/python" "$ROOT/scripts/setup_fdb.py" --destination "$ROOT/vendor/Full-Duplex-Bench"
if [[ " ${*:-} " != *" --check "* ]]; then
  "$VENV/bin/python" -m pip install "nemo_toolkit[asr]==2.5.3" "pydub==0.25.1" "ffmpeg-python==0.2.0"
fi
exec "$VENV/bin/python" "$ROOT/scripts/reproduce.py" "$@"
