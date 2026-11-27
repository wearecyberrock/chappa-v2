# Chappa V2 — Autonomous Cybersecurity Agent

**Chappa V2** is a standalone, local-first Cybersecurity Agent built on top of **Hermes** (`Antigravity`, local `Ollama`, or API models), combining:
- **Red Matrix (`1` & `0`) 3D Hacker Mask Command Center** (WebGL2 PBR sculpted 3D mask, cascading crimson binary rain, `12fps` / `60fps` cadence, drop-in `~/.chappa/modules/custom_mask.obj`)
- **Defensive Posture & IOC Telemetry** (Read-only DNS, TLS certificate, and HTTP security header posture checks + `/api/chappa/telemetry/ingest`)
- **God's Eye View** (Red Matrix 3D Geospatial Globe plotting live SOC alerts, ASNs, and correlation arcs)
- **Vigil AI SOC** (Local SQLite IOC triage, MITRE ATT&CK mapping, and containment playbooks)
- **Hot-Upgradable Modules (`~/.chappa/modules/`):** Install or upgrade defensive playbooks, custom `.obj` masks, and UI modules without rebuilding the `.exe` / `.dmg`.

## Quick Start (Standalone)
```bash
./start.sh
# Opens at http://127.0.0.1:7480
```
When launched by **Assimilis**, Chappa V2 automatically bridges to `ASSIMILIS_URL` for unified SSO, `/api/models/all`, and multi-agent delegation.
