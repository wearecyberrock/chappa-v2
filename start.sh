#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CHAPPA_HOST="${CHAPPA_HOST:-127.0.0.1}"
export CHAPPA_PORT="${CHAPPA_PORT:-7480}"
exec python3 "$DIR/chappa_server.py"
