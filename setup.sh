#!/usr/bin/env bash
# One-command local bootstrap for Chappa V2 (macOS & Linux, zero Docker required)
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

echo "==> [1/5] Syncing Full Vigil AI SOC & Full God's Eye View submodules…"
git submodule update --init --recursive

echo "==> [2/5] Installing & building Full God's Eye View (apps/gods-eye-view)…"
(
  cd "$ROOT_DIR/apps/gods-eye-view"
  npm install --no-audit --no-fund
  if [ -f "node_modules/esbuild/install.js" ]; then
    node node_modules/esbuild/install.js || true
  fi
  npm run build
)

echo "==> [3/5] Installing Full Vigil AI SOC Python environment (apps/vigil/.venv)…"
(
  cd "$ROOT_DIR/apps/vigil"
  if [ ! -d ".venv" ]; then
    python3 -m venv .venv
  fi
  .venv/bin/pip install --upgrade pip -q
  .venv/bin/pip install -r requirements.txt
)

echo "==> [4/5] Building Full Vigil React SOC Console (VITE_DEV_MODE=true)…"
(
  cd "$ROOT_DIR/apps/vigil/clients/web"
  npm install --no-audit --no-fund
  VITE_DEV_MODE=true npm run build
)

echo "==> [5/5] Verifying local zero-root PostgreSQL & Redis…"
python3 -c '
import runtime_manager as rm
pg = rm.MANAGER.ensure_postgres()
rd = rm.MANAGER.ensure_redis()
print(f"PostgreSQL (127.0.0.1:{rm.PG_PORT}):", "OK" if pg else "NOT FOUND (install postgresql via brew/apt)")
print(f"Redis      (127.0.0.1:{rm.REDIS_PORT}):", "OK" if rd else "OPTIONAL (install redis via brew/apt for faster boot & ARQ worker)")
'

echo ""
echo "✓ Chappa V2 Full setup complete! Run ./start.sh to launch:"
echo "  - Chappa V2 Hermes Core:    http://127.0.0.1:7480/"
echo "  - Full Vigil AI SOC:        http://127.0.0.1:7480/vigil/"
echo "  - Full God'\''s Eye View (3D): http://127.0.0.1:7480/godseye/?embed=1"
