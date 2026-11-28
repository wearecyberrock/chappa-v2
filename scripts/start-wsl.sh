#!/usr/bin/env bash
# Run chappa inside WSL/Linux, where the pentest catalog actually works.
#
# Binds loopback inside WSL; WSL2 forwards that to localhost on Windows, so the
# browser on the Windows side opens the same URL. Nothing is exposed to the LAN.
#
# Env overrides: CHAPPA_PORT, CHAPPA_HOST, CHAPPA_ALLOW_RED, CHAPPA_ALLOW_SHELL,
#                CHAPPA_VENV
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${CHAPPA_VENV:-$HOME/.chappa/venv}"

if [ ! -x "$VENV/bin/python" ]; then
  echo "error: no virtualenv at $VENV" >&2
  echo "run:   bash scripts/wsl-bootstrap.sh" >&2
  exit 1
fi

export CHAPPA_HOST="${CHAPPA_HOST:-127.0.0.1}"
export CHAPPA_PORT="${CHAPPA_PORT:-7480}"
export CHAPPA_ALLOW_RED="${CHAPPA_ALLOW_RED:-1}"
export CHAPPA_ALLOW_SHELL="${CHAPPA_ALLOW_SHELL:-1}"

echo "[chappa] python: $("$VENV/bin/python" -V 2>&1)"
exec "$VENV/bin/python" "$DIR/chappa_server.py"
