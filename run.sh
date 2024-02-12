#!/bin/bash
set -e -u
export PGDATABASE="${PGDATABASE:-}"
export PGUSER="${PGUSER:-$(whoami)}"
export PGHOST=localhost

HERE="$(dirname "$0")"
VENV="${VENV:-$HERE/.venv}"

# Creating a virtual environment if it doesn't exist
if [ ! -d "$VENV" ]; then
    python3 -m venv "$VENV"
    "$VENV"/bin/pip install -r "$HERE/web/requirements.txt"
fi

"$VENV/bin/uvicorn" --host 0.0.0.0 --port 8000 web.main:app
