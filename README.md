# Chappa V2 — Autonomous Cybersecurity Agent

**Chappa V2** is a standalone, local-first Cybersecurity Agent built on top of **Hermes** (`Antigravity`, local `Ollama`, or API models), combining:
- **3D Hacker Mask Command Center** (Agentsar × Spider-Verse holographic UI, `12fps` / `60fps` cadence)
- **HackingTool v2** (Recon & Audit runner with approval gate + TUI drawer)
- **God's Eye View** (3D Geospatial Globe plotting targets, ASNs, and traceroute arcs)
- **Vigil AI SOC** (In-process SQLite IOC triage, MITRE ATT&CK mapping, and playbooks)
- **Hot-Upgradable Modules (`~/.chappa/modules/`):** Install or upgrade tools, playbooks, and UI artifacts without rebuilding the `.exe` / `.dmg`.

## Quick Start (Standalone)
```bash
./start.sh
# Opens at http://127.0.0.1:7480
```
When launched by **Assimilis**, Chappa V2 automatically bridges to `ASSIMILIS_URL` for unified SSO, `/api/models/all`, and multi-agent delegation.
