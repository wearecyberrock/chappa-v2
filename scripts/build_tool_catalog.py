#!/usr/bin/env python3
"""Build chappa's unified tool catalog from the vendored hackingtool tree.

Why a build step: chappa's server is stdlib-only by design (it ships as one
file and runs on a bare Python), while the catalog lives in hackingtool's
Python classes and YAML overlays, which need `rich`/`textual`/`yaml` to import.
So the catalog is compiled here into `tools_catalog.json` and the server reads
plain JSON at runtime.

Sources, in order:
  1. Python tool classes under hackingtool_v2/src/hackingtool/tools/**/*.py,
     read with `ast` (no import ⇒ no UI dependencies at build time).
  2. The YAML catalog files, including the blue-team categories, which either
     merge into an existing collection (`merge_into`) or add a new category.

Team classification (red / blue / both) is derived, not hand-maintained:
  - an explicit `team:` on a category header wins;
  - otherwise a category is blue if its title carries a defensive hint,
    red if not;
  - a tool is promoted to `both` when its tags straddle the two sides
    (e.g. `vuln-scan` + `reporting` under an offensive category).

Run:  py -3 scripts/build_tool_catalog.py [--check]
      (needs PyYAML; `--check` exits non-zero if the committed JSON is stale)
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
HT = REPO / "hackingtool_v2"
SRC = HT / "src" / "hackingtool"
TOOLS_DIR = SRC / "tools"
CATALOG_DIR = SRC / "catalog"
OUT = REPO / "tools_catalog.json"

# Tags that mean "this is defensive work" and "this is offensive work". A tool
# whose tags hit both sides is dual-use.
BLUE_TAGS = {
    "detection", "monitoring", "log-analysis", "threat-hunting", "threat-intel",
    "triage", "incident-response", "containment", "evidence-collection",
    "hardening", "compliance", "vulnerability-management",
    "forensics", "malware-analysis",
}
RED_TAGS = {
    "exploitation", "post-exploitation", "payload", "c2", "phishing", "ddos",
    "privesc", "lateral-movement", "persistence", "credentials",
    "password-attack", "bruteforce", "hash-crack", "sql-injection", "xss",
    "social-engineering", "reverse-shell", "exfiltration", "wordlist",
    "anonymity", "mitm", "relay", "poisoning", "adcs", "kerberos",
}
BLUE_CATEGORY_HINTS = (
    "forensic", "detection", "monitoring", "incident", "threat intel",
    "threat hunt", "hardening", "compliance", "malware", "vulnerability",
    "defensive", "blue",
)
# Matched as whole words, not substrings: "catalog overlays" must not read as
# a logging category just because "log " appears inside "catalog ".
BLUE_CATEGORY_WORDS = {"log", "logs", "logging"}

PHASE_TAGS = (
    "recon", "osint", "scanner", "port-scan", "subdomain-enum", "vuln-scan",
    "fingerprint", "crawler", "enumeration", "exploitation",
    "post-exploitation", "privesc", "lateral-movement", "persistence",
    "reporting", "detection", "monitoring", "log-analysis", "threat-hunting",
    "threat-intel", "triage", "incident-response", "containment",
    "evidence-collection", "hardening", "compliance",
    "vulnerability-management",
)

# `<target>` style slots a catalog command declares; the server fills these and
# nothing else (the slot list is the whole contract between UI and executor).
PLACEHOLDER_RE = re.compile(r"<([A-Za-z][A-Za-z0-9_\-]{0,31})>")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "unnamed"


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _const(node: ast.AST):
    """Return a literal for a simple constant/list/dict node, else None."""
    try:
        return ast.literal_eval(node)
    except Exception:
        return None


def scan_python() -> tuple[list[dict], dict[str, str], dict[str, list[str]]]:
    """Return (tool_classes, class->module, collection_title->tool class names)."""
    tool_classes: dict[str, dict] = {}
    class_module: dict[str, str] = {}
    collections: dict[str, list[str]] = {}

    for path in sorted(TOOLS_DIR.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            bases = {getattr(b, "id", None) or getattr(b, "attr", None) for b in node.bases}
            attrs: dict[str, object] = {}
            for stmt in node.body:
                if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                    target = stmt.targets[0]
                    if isinstance(target, ast.Name):
                        value = _const(stmt.value)
                        if value is not None:
                            attrs[target.id] = value
            if "HackingTool" in bases:
                tool_classes[node.name] = attrs
                class_module[node.name] = path.stem
            elif "HackingToolsCollection" in bases:
                order = []
                toks = attrs.get("TOOLS")
                # TOOLS may be a list of calls: [Foo(), Bar()] — literal_eval
                # cannot see those, so read calls directly from the AST.
                for stmt in node.body:
                    if (
                        isinstance(stmt, ast.Assign)
                        and isinstance(stmt.targets[0], ast.Name)
                        and stmt.targets[0].id == "TOOLS"
                        and isinstance(stmt.value, ast.List)
                    ):
                        for elt in stmt.value.elts:
                            if isinstance(elt, ast.Call) and isinstance(elt.func, ast.Name):
                                order.append(elt.func.id)
                if order:
                    collections[node.name] = order
                if attrs.get("TITLE"):
                    collections.setdefault(f"__title__{node.name}", [str(attrs["TITLE"])])
    return (
        [{"name": k, **v} for k, v in tool_classes.items()],
        class_module,
        collections,
    )


def collection_titles(collections: dict[str, list[str]]) -> dict[str, str]:
    """collection class name -> its TITLE string (carried in a marker entry)."""
    out = {}
    for key, val in collections.items():
        if key.startswith("__title__") and len(val) == 1 and isinstance(val[0], str):
            out[key[len("__title__"):]] = val[0]
    return out


def load_yaml_catalog() -> tuple[list[dict], dict[str, dict]]:
    """Return (yaml categories, overlay map keyed by normalized title)."""
    categories: list[dict] = []
    overlays: dict[str, dict] = {}
    for path in sorted(CATALOG_DIR.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:  # a broken catalog must fail the build loudly
            raise SystemExit(f"invalid YAML in {path.name}: {exc}") from exc
        header = data.get("category") or {}
        tools = [t for t in (data.get("tools") or []) if isinstance(t, dict)]
        if header or tools:
            categories.append(
                {
                    "file": path.name,
                    "title": header.get("title") or path.stem,
                    "icon": header.get("icon"),
                    "description": header.get("description", ""),
                    "merge_into": header.get("merge_into"),
                    "team": header.get("team"),
                    "tools": tools,
                }
            )
        for entry in data.get("overlay") or []:
            if isinstance(entry, dict) and entry.get("title"):
                key = norm(entry["title"])
                merged = overlays.setdefault(key, {"_title": entry["title"]})
                for field, value in entry.items():
                    if field != "title":
                        merged[field] = value
    return categories, overlays


def category_team(title: str, explicit: str | None) -> str:
    if explicit in ("red", "blue", "both"):
        return explicit
    low = norm(title)
    if any(h in low for h in BLUE_CATEGORY_HINTS):
        return "blue"
    if BLUE_CATEGORY_WORDS.intersection(re.findall(r"[a-z]+", low)):
        return "blue"
    return "red"


def tool_team(base: str, tags: list[str]) -> str:
    hits_blue = bool(BLUE_TAGS.intersection(tags))
    hits_red = bool(RED_TAGS.intersection(tags))
    if hits_blue and hits_red:
        return "both"
    if base == "red" and hits_blue:
        return "both"
    if base == "blue" and hits_red:
        return "both"
    return base


def phase_of(tags: list[str], team: str) -> str:
    for tag in tags:
        if tag in PHASE_TAGS:
            return tag
    return "detection" if team == "blue" else "recon"


def build() -> dict:
    classes, modules, collections = scan_python()
    titles = collection_titles(collections)
    by_name = {c["name"]: c for c in classes}

    # category title -> tool records, preserving menu order
    cats: dict[str, dict] = {}

    def ensure_cat(title: str, **meta) -> dict:
        key = norm(title)
        if key not in cats:
            cats[key] = {
                "id": slug(title),
                "title": title,
                "team": meta.get("team") or category_team(title, None),
                "description": meta.get("description") or "",
                "icon": meta.get("icon") or "",
                "tools": [],
            }
        return cats[key]

    # 1) Python collections → categories. A collection nested inside another
    #    (Other tools → Android Hacking tools) stays its own category and is
    #    not also copied into the parent, so every tool appears exactly once.
    nested = {
        member
        for members in collections.values()
        for member in members
        if member in collections
    }
    for coll_name, member_names in collections.items():
        if coll_name.startswith("__title__"):
            continue
        title = titles.get(coll_name, coll_name)
        if "update or uninstall" in norm(title):
            continue  # tooling for hackingtool itself, not a security capability
        cat = ensure_cat(title)
        for member in member_names:
            if member in collections:  # nested: owned by its own category
                continue
            rec = by_name.get(member)
            if rec:
                cat["tools"].append(_py_tool(rec, modules.get(member, "")))

    # 2) YAML categories: merge into an existing collection, or add a new one
    yaml_cats, overlays = load_yaml_catalog()
    for ycat in yaml_cats:
        target = ycat.get("merge_into")
        if target:
            match = next((c for c in cats.values() if norm(c["title"]) == norm(target)), None)
            if match is None:
                match = ensure_cat(target)
            if ycat.get("team"):
                match["team"] = ycat["team"]
            cat = match
        else:
            cat = ensure_cat(
                ycat["title"],
                team=ycat.get("team"),
                description=ycat.get("description"),
                icon=ycat.get("icon"),
            )
        for entry in ycat["tools"]:
            cat["tools"].append(_yaml_tool(entry, cat["title"], ycat["file"]))

    # 3) Overlays enrich existing tools by title; unheard-of titles become
    #    standalone entries so no guidance in the catalog is silently dropped.
    def strip_qualifier(title: str) -> str:
        return norm(re.sub(r"\s*\([^)]*\)", " ", title or ""))

    by_norm: dict[str, dict] = {}
    by_first: dict[str, dict] = {}
    for cat in cats.values():
        for t in cat["tools"]:
            by_norm.setdefault(norm(t["title"]), t)
            first = norm(t["title"]).split(" ")[0] if norm(t["title"]) else ""
            if len(first) >= 5:
                # only keep unambiguous first tokens
                by_first[first] = t if first not in by_first else None

    for key, overlay in sorted(overlays.items()):
        title = overlay.get("_title") or key
        rec = by_norm.get(key) or by_norm.get(strip_qualifier(title))
        if rec is None:
            first = strip_qualifier(title).split(" ")[0]
            candidate = by_first.get(first)
            rec = candidate if isinstance(candidate, dict) else None
        if rec is not None:
            rec["tags"] = list(dict.fromkeys(rec["tags"] + list(overlay.get("tags") or [])))
            rec["usage"] = [list(u) for u in (overlay.get("usage") or rec["usage"])]
            if overlay.get("lab_safe_notes"):
                rec["notes"] = overlay["lab_safe_notes"]
            rec["source"] = rec["source"] + "+overlay"
        else:
            cat = ensure_cat("Catalog Overlays")
            tags = list(overlay.get("tags") or [])
            cat["tools"].append(
                {
                    "id": f"{cat['id']}/{slug(key)}",
                    "title": title,
                    "category": cat["title"],
                    "category_id": cat["id"],
                    "team": "both",
                    "phase": "recon",
                    "tags": tags,
                    "run": [],
                    "usage": [list(u) for u in (overlay.get("usage") or [])],
                    "description": "",
                    "notes": overlay.get("lab_safe_notes", ""),
                    "url": "",
                    "source": "catalog-overlay",
                    "installable": False,
                    "archived": False,
                    "kind": "install",
                }
            )

    # 4) finalize: team/phase per tool, drop empties, dedupe ids
    out_tools: list[dict] = []
    used: dict[str, int] = {}
    for cat in cats.values():
        for rec in cat["tools"]:
            tags = [t for t in rec.get("tags") or [] if isinstance(t, str)]
            rec["tags"] = tags
            if cat["team"] == "both":
                tb = bool(BLUE_TAGS.intersection(tags))
                tr = bool(RED_TAGS.intersection(tags))
                rec["team"] = "both" if tb == tr else ("blue" if tb else "red")
            else:
                rec["team"] = tool_team(cat["team"], tags)
            rec["phase"] = phase_of(tags, rec["team"])
            rec["category"] = cat["title"]
            rec["category_id"] = cat["id"]
            base = rec["id"]
            if base in used:
                used[base] += 1
                rec["id"] = f"{base}-{used[base]}"
            else:
                used[base] = 1
            # Parameter slots come from the catalog's own commands; the server
            # only fills slots that are declared here.
            declared_cmds = list(rec.get("run") or []) + [
                u[1] for u in (rec.get("usage") or []) if len(u) == 2
            ]
            rec["params"] = sorted(
                {m for cmd in declared_cmds for m in PLACEHOLDER_RE.findall(str(cmd))}
            )
            out_tools.append(rec)
        cat["tool_count"] = len(cat["tools"])
        if not cat["description"]:
            cat["description"] = ""
        del cat["tools"]

    tools = [t for t in out_tools if t["title"]]
    categories = [c for c in cats.values() if c.get("tool_count")]
    stats = {
        "tools": len(tools),
        "categories": len(categories),
        "red": sum(1 for t in tools if t["team"] == "red"),
        "blue": sum(1 for t in tools if t["team"] == "blue"),
        "both": sum(1 for t in tools if t["team"] == "both"),
        "runnable": sum(1 for t in tools if t["run"]),
    }
    return {
        "schema": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {
            "hackingtool": str(HT.name),
            "catalog_files": len(list(CATALOG_DIR.glob("*.yaml"))),
            "python_modules": len(list(TOOLS_DIR.rglob("*.py"))),
        },
        "stats": stats,
        "categories": categories,
        "tools": tools,
    }


def _py_tool(rec: dict, module: str) -> dict:
    title = str(rec.get("TITLE") or rec["name"])
    run = [c for c in (rec.get("RUN_COMMANDS") or []) if isinstance(c, str)]
    install = [c for c in (rec.get("INSTALL_COMMANDS") or []) if isinstance(c, str)]
    return {
        "id": f"py/{slug(title)}",
        "title": title,
        "team": "red",
        "phase": "recon",
        "tags": [],
        "run": run,
        "usage": [],
        "description": str(rec.get("DESCRIPTION") or ""),
        "notes": "",
        "url": str(rec.get("PROJECT_URL") or ""),
        "source": f"python:{module}" if module else "python",
        "installable": bool(install),
        "archived": bool(rec.get("ARCHIVED")),
        "kind": "install",
    }


def _yaml_tool(entry: dict, category: str, file: str) -> dict:
    title = str(entry.get("title") or "untitled")
    usage = [list(u) for u in (entry.get("usage") or []) if len(u) == 2]
    return {
        "id": f"yaml/{slug(title)}",
        "title": title,
        "team": "red",
        "phase": "recon",
        "tags": list(entry.get("tags") or []),
        "run": [c for c in (entry.get("run") or []) if isinstance(c, str)],
        "usage": usage,
        "description": str(entry.get("description") or ""),
        "notes": str(entry.get("lab_safe_notes") or ""),
        "url": str(entry.get("project_url") or entry.get("url") or ""),
        "source": f"catalog:{file}",
        "installable": bool(entry.get("install") or entry.get("system_pkgs")),
        "archived": False,
        "kind": str(entry.get("kind") or "install"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="fail if the committed JSON is stale")
    args = ap.parse_args()

    if not TOOLS_DIR.is_dir():
        print(f"error: hackingtool tree not found at {TOOLS_DIR}", file=sys.stderr)
        return 2
    data = build()
    rendered = json.dumps(data, indent=2, sort_keys=False) + "\n"

    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.is_file() else ""
        if current != rendered:
            print("stale: tools_catalog.json does not match the sources", file=sys.stderr)
            return 1
        print("up to date")
        return 0

    OUT.write_text(rendered, encoding="utf-8")
    digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest()[:12]
    s = data["stats"]
    print(f"wrote {OUT.name} sha256:{digest}")
    print(
        f"  {s['tools']} tools across {s['categories']} categories — "
        f"red {s['red']}, blue {s['blue']}, both {s['both']}, runnable {s['runnable']}"
    )
    for cat in data["categories"]:
        print(f"  {cat['team']:<4} {cat['title']}: {cat['tool_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
