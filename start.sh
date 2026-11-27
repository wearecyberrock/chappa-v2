#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export CHAPPA_HOST="${CHAPPA_HOST:-127.0.0.1}"
export CHAPPA_PORT="${CHAPPA_PORT:-7480}"
export CHAPPA_AUTO_START_APPS="${CHAPPA_AUTO_START_APPS:-1}"
exec python3 chappa_server.py
