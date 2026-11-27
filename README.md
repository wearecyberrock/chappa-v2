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

## Unified Tool Plane (red + blue)

`hackingtool_v2/` is vendored as a git subtree. Chappa never imports it: `scripts/build_tool_catalog.py` compiles its Python tool classes and YAML catalogs — including the blue-team categories added under `hackingtool_v2/src/hackingtool/catalog/blue_*.yaml` — into `tools_catalog.json`, which the server reads with **no third-party dependencies**.

Current catalog: **315 tools in 39 categories — 253 red, 46 blue, 16 dual-use**.

| Endpoint | Purpose |
|---|---|
| `GET /api/chappa/tools` | filter by `team=red\|blue\|both`, `category=`, `phase=`, `q=` |
| `POST /api/chappa/tools/run` | `{id, command?, params?, timeout_s?, dry_run?, allow_red?}` |
| `GET /api/chappa/tools/runs?limit=20` | audit trail |

Execution rules, enforced in `chappa_tools.py`:

- **No shell, ever** — a command is parsed to argv and run with `shell=False`.
- **The catalog is the allowlist** — an entry may only run a binary it already declares.
- **Blue always runs; red needs an engagement** — `CHAPPA_ALLOW_RED=1`, a recorded `active_target`, and a state other than `IDLE`.
- **Templates are refused** — commands containing pipes or redirects are rejected rather than handed to a shell.
- **Parameters are catalog-declared** — `<target>`-style slots come from the entry, values are restricted to `[A-Za-z0-9._:/@%=+\-]`, and a red-team run must still contain the recorded target (help/version introspection excepted).
- **Everything is audited** — accepted and refused attempts land in the SQLite `tool_runs` table and on the SSE bus as `tool_run`.

### Reaching the tools

- **Agent:** the chat prompt carries a catalog briefing; the agent (or the operator typing directly) issues `[[search <keywords>]]` or `[[run <tool_id> key=value ...]]`. Chat directives pass the same gate as the HTTP API, so the model cannot bypass authorization.
- **UI:** the **Tools** drawer pane browses the catalog with team filters and search, exposes each entry's declared parameters, and offers Dry/Run with live output.

Rebuild after changing a catalog file:

```bash
py -3 scripts/build_tool_catalog.py          # needs PyYAML
py -3 scripts/build_tool_catalog.py --check  # CI: fail if the JSON is stale
```
