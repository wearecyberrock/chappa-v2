# Chappa V2 — Standalone Local-First Cybersecurity Agent

A standalone, downloadable Cybersecurity Command Core powered by **Hermes**, unifying:

- **Red Matrix Floating 3D `1` & `0` Particle Hacker Mask Core** — WebGL2 pure floating binary particle cloud using Assimilis Holo Particle physics (hover parting/swirl, acoustic voice ripples, glowing crimson almond eyes synced live to Assimilis Fish Audio / Voice Studio, custom `.obj` morphing via `~/.chappa/modules/custom_mask.obj`).
- **Full Vigil AI SOC (`apps/vigil`)** — Complete upstream FastAPI + PostgreSQL + React SOC Console, specialist agents, Markdown `WORKFLOW.md` playbooks, and `/mcp` server (auth bypassed via `DEV_MODE=true` behind Assimilis's one login, zero-root local PostgreSQL at `~/.chappa/pgdata` + Redis at `~/.chappa/redis`). Served live inside Chappa V2 at `/vigil/` (and `/chappa-v2/vigil/` behind Assimilis).
- **Full God's Eye View (`apps/gods-eye-view`)** — Complete upstream photorealistic 3D Cesium globe, live geospatial feeds (aircraft, ships, satellites, earthquakes, weather, datacenters, CCTV), and `/mcp` server. Served live inside Chappa V2 at `/godseye/?embed=1` (and `/chappa-v2/godseye/?embed=1` behind Assimilis).
- **Real Hermes Engine** — Multi-turn LLM orchestration via Assimilis's unified model router (`/api/models/all` + `/api/world/models/complete`, including Antigravity & local Ollama) or standalone `~/.hermes/.env`, with live tool calls driving Full Vigil and Full God's Eye View.
- **Defensive Posture & Telemetry** — Strictly defensive, read-only DNS / TLS certificate / HTTP security-header inspection that ingests real findings into Full Vigil and plots coordinates on Full God's Eye View.

## Quick Start (macOS / Linux — Zero Docker)

```bash
git clone --recurse-submodules https://github.com/wearecyberrock/chappa-v2.git
cd chappa-v2
chmod +x setup.sh start.sh
./setup.sh
./start.sh
```

Then open:
- **Chappa V2 Hermes Core:** `http://127.0.0.1:7480/`
- **Full Vigil AI SOC:** `http://127.0.0.1:7480/vigil/`
- **Full God's Eye View:** `http://127.0.0.1:7480/godseye/?embed=1`

When Assimilis (`wearecyberrock/Elevedenbot`) is running on the same machine, Assimilis automatically connects to Chappa V2 at `/chappa-v2/` behind Assimilis's single login.

## Upstream Licences

Upstream submodules under `apps/vigil` (Apache-2.0) and `apps/gods-eye-view` (MIT) keep their original `LICENSE` and `THIRD_PARTY_NOTICES.md` files unmodified.
