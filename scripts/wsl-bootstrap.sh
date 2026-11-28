#!/usr/bin/env bash
# Prepare chappa to run inside WSL/Linux.
#
# Creates an isolated virtualenv under ~/.chappa/venv (never touches the
# system Python, which is externally managed on modern Ubuntu) and installs
# the vendored hackingtool package with its dependencies into it. Chappa
# itself needs nothing beyond the standard library — only the tool catalog
# does.
#
# Usage:  bash scripts/wsl-bootstrap.sh
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${CHAPPA_VENV:-$HOME/.chappa/venv}"

echo "repo:  $DIR"
echo "venv:  $VENV"

if [ ! -x "$VENV/bin/python" ]; then
  echo "==> creating virtualenv"
  python3 -m venv "$VENV"
fi

echo "==> upgrading pip"
"$VENV/bin/pip" install --quiet --upgrade pip

echo "==> installing hackingtool (editable) + dependencies"
"$VENV/bin/pip" install --quiet -e "$DIR/hackingtool_v2"

echo "==> verifying"
"$VENV/bin/python" - <<'PY'
import importlib.util, sys
print("python:", sys.version.split()[0])
for mod in ("hackingtool", "yaml", "rich", "textual", "prompt_toolkit"):
    print(f"  {mod:<16}", "ok" if importlib.util.find_spec(mod) else "MISSING")
PY

echo
echo "Ready. Start the UI with:  bash scripts/start-wsl.sh"
