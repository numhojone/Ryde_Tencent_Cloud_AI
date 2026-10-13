#!/usr/bin/env bash
# Start RydeResolve. Loads .env if present; without a key it runs in deterministic mode.
set -e
cd "$(dirname "$0")"
if [ -f .env ]; then set -a; . ./.env; set +a; fi
export PYTHONPATH="$(pwd):$PYTHONPATH"
exec python3 -m app.main "$@"
