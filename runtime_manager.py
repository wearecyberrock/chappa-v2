"""Zero-root local runtime supervisor for Chappa V2's full upstream apps.

Manages:
  1. Local user-owned PostgreSQL 16 cluster (~/.chappa/pgdata on 127.0.0.1:15432)
  2. Local user-owned Redis server (~/.chappa/redis on 127.0.0.1:16379)
  3. Full Vigil AI SOC backend + React console (apps/vigil on 127.0.0.1:16987)
  4. Full God's Eye View 3D Cesium globe + providers + MCP (apps/gods-eye-view on 127.0.0.1:14173)

Works on both Linux and macOS without Docker or root privileges at runtime.
"""
from __future__ import annotations

import atexit
import glob
import os
import shutil
import socket
import subprocess
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent
APPS_DIR = ROOT / "apps"
VIGIL_DIR = APPS_DIR / "vigil"
GODSEYE_DIR = APPS_DIR / "gods-eye-view"

STATE_DIR = Path(os.environ.get("CHAPPA_STATE_DIR") or (Path.home() / ".chappa")).expanduser()
LOGS_DIR = STATE_DIR / "logs"
PGDATA_DIR = STATE_DIR / "pgdata"
PGRUN_DIR = STATE_DIR / "pgrun"
REDIS_DIR = STATE_DIR / "redis"

PG_HOST = os.environ.get("CHAPPA_PG_HOST", "127.0.0.1")
PG_PORT = int(os.environ.get("CHAPPA_PG_PORT", "15432"))
PG_DB = os.environ.get("CHAPPA_PG_DB", "deeptempo_soc")
PG_USER = os.environ.get("CHAPPA_PG_USER", "deeptempo")
PG_PASSWORD = os.environ.get("CHAPPA_PG_PASSWORD", "deeptempo_secure_password_change_me")

REDIS_HOST = os.environ.get("CHAPPA_REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("CHAPPA_REDIS_PORT", "16379"))

VIGIL_HOST = os.environ.get("CHAPPA_VIGIL_HOST", "127.0.0.1")
VIGIL_PORT = int(os.environ.get("CHAPPA_VIGIL_PORT", "16987"))
VIGIL_URL = os.environ.get("VIGIL_URL", f"http://{VIGIL_HOST}:{VIGIL_PORT}").rstrip("/")

GODSEYE_HOST = os.environ.get("CHAPPA_GODSEYE_HOST", "127.0.0.1")
GODSEYE_PORT = int(os.environ.get("CHAPPA_GODSEYE_PORT", "14173"))
GODSEYE_URL = os.environ.get("GODSEYE_URL", f"http://{GODSEYE_HOST}:{GODSEYE_PORT}").rstrip("/")


def _tcp_open(host: str, port: int, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _http_ok(url: str, timeout: float = 0.8) -> bool:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return 200 <= r.status < 500
    except Exception:
        return False


def _find_pg_bin(name: str) -> str | None:
    direct = shutil.which(name)
    if direct:
        return direct
    patterns = [
        f"/usr/lib/postgresql/*/bin/{name}",
        f"/opt/homebrew/opt/postgresql*/bin/{name}",
        f"/usr/local/opt/postgresql*/bin/{name}",
        f"/Library/PostgreSQL/*/bin/{name}",
    ]
    for pat in patterns:
        matches = sorted(glob.glob(pat), reverse=True)
        for m in matches:
            if os.access(m, os.X_OK):
                return m
    return None


def _vigil_uvicorn_bin() -> str | None:
    candidates = [
        VIGIL_DIR / ".venv" / "bin" / "uvicorn",
        VIGIL_DIR / ".venv" / "Scripts" / "uvicorn.exe",
    ]
    for c in candidates:
        if c.is_file() and os.access(c, os.X_OK):
            return str(c)
    return shutil.which("uvicorn")


def _godseye_vite_cmd() -> list[str] | None:
    local_vite = GODSEYE_DIR / "node_modules" / ".bin" / "vite"
    if local_vite.is_file() and os.access(local_vite, os.X_OK):
        return [str(local_vite), "preview", "--host", GODSEYE_HOST, "--port", str(GODSEYE_PORT), "--strictPort"]
    npx = shutil.which("npx")
    if npx:
        return [npx, "vite", "preview", "--host", GODSEYE_HOST, "--port", str(GODSEYE_PORT), "--strictPort"]
    return None


class RuntimeManager:
    """Supervises local Postgres, Redis, Full Vigil AI SOC, and Full God's Eye View."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._procs: dict[str, subprocess.Popen[Any]] = {}
        self._logs: dict[str, Any] = {}
        self._errors: dict[str, str] = {}
        self._booting: set[str] = set()
        self._on_change: Callable[[dict[str, Any]], None] | None = None
        atexit.register(self.shutdown_children)

    def _emit_change(self) -> None:
        cb = self._on_change
        if cb:
            try:
                cb(self.status())
            except Exception:
                pass

    def ensure_postgres(self) -> bool:
        if _tcp_open(PG_HOST, PG_PORT):
            self._errors.pop("postgres", None)
            return True
        pg_ctl = _find_pg_bin("pg_ctl")
        initdb = _find_pg_bin("initdb")
        psql = _find_pg_bin("psql")
        if not pg_ctl:
            self._errors["postgres"] = "PostgreSQL (pg_ctl) not installed — run ./setup.sh"
            return False

        STATE_DIR.mkdir(parents=True, exist_ok=True)
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        PGRUN_DIR.mkdir(parents=True, exist_ok=True)
        pg_log = LOGS_DIR / "postgres.log"

        try:
            fresh = not (PGDATA_DIR / "PG_VERSION").is_file()
            if fresh:
                if not initdb:
                    self._errors["postgres"] = "PostgreSQL initdb not found"
                    return False
                PGDATA_DIR.mkdir(parents=True, exist_ok=True)
                subprocess.run(
                    [initdb, "-D", str(PGDATA_DIR), "-A", "trust", "-E", "UTF8", "--no-locale"],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            opts = f"-h {PG_HOST} -p {PG_PORT} -k {PGRUN_DIR}"
            subprocess.run(
                [pg_ctl, "-D", str(PGDATA_DIR), "-l", str(pg_log), "-o", opts, "start"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            for _ in range(30):
                if _tcp_open(PG_HOST, PG_PORT):
                    break
                time.sleep(0.2)
            if not _tcp_open(PG_HOST, PG_PORT):
                self._errors["postgres"] = f"PostgreSQL failed to bind {PG_HOST}:{PG_PORT} (check {pg_log})"
                return False

            if psql:
                # Ensure role and database exist idempotently
                role_sql = (
                    f"DO $$ BEGIN "
                    f"IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{PG_USER}') THEN "
                    f"CREATE ROLE {PG_USER} WITH LOGIN SUPERUSER PASSWORD '{PG_PASSWORD}'; "
                    f"END IF; END $$;"
                )
                subprocess.run(
                    [psql, "-h", PG_HOST, "-p", str(PG_PORT), "-d", "postgres", "-c", role_sql],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                chk = subprocess.run(
                    [psql, "-h", PG_HOST, "-p", str(PG_PORT), "-d", "postgres", "-tAc", f"SELECT 1 FROM pg_database WHERE datname='{PG_DB}'"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if "1" not in (chk.stdout or ""):
                    subprocess.run(
                        [psql, "-h", PG_HOST, "-p", str(PG_PORT), "-d", "postgres", "-c", f"CREATE DATABASE {PG_DB} OWNER {PG_USER};"],
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
            self._errors.pop("postgres", None)
            return True
        except Exception as exc:
            self._errors["postgres"] = str(exc)
            return False

    def ensure_redis(self) -> bool:
        if _tcp_open(REDIS_HOST, REDIS_PORT):
            self._errors.pop("redis", None)
            return True
        redis_bin = shutil.which("redis-server")
        if not redis_bin:
            self._errors["redis"] = "redis-server not installed (optional; Vigil still boots without it)"
            return False
        REDIS_DIR.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                [
                    redis_bin,
                    "--bind", REDIS_HOST,
                    "--port", str(REDIS_PORT),
                    "--dir", str(REDIS_DIR),
                    "--daemonize", "yes",
                    "--save", "",
                    "--appendonly", "no",
                ],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            for _ in range(15):
                if _tcp_open(REDIS_HOST, REDIS_PORT):
                    self._errors.pop("redis", None)
                    return True
                time.sleep(0.15)
            self._errors["redis"] = f"Redis failed to bind {REDIS_HOST}:{REDIS_PORT}"
            return False
        except Exception as exc:
            self._errors["redis"] = str(exc)
            return False

    def start_vigil(self, wait_seconds: float = 0.0) -> bool:
        if _http_ok(f"{VIGIL_URL}/api/health", timeout=0.6):
            self._errors.pop("vigil", None)
            return True
        if not (VIGIL_DIR / "services" / "api" / "main.py").is_file():
            self._errors["vigil"] = "apps/vigil submodule missing — run ./setup.sh"
            return False
        uvicorn_bin = _vigil_uvicorn_bin()
        if not uvicorn_bin:
            self._errors["vigil"] = "apps/vigil/.venv not built — run ./setup.sh"
            return False

        self.ensure_postgres()
        self.ensure_redis()

        with self._lock:
            existing = self._procs.get("vigil")
            if existing and existing.poll() is None:
                pass
            else:
                LOGS_DIR.mkdir(parents=True, exist_ok=True)
                log_fp = open(LOGS_DIR / "vigil.log", "ab")
                self._logs["vigil"] = log_fp
                env = os.environ.copy()
                chappa_port = os.environ.get("CHAPPA_PORT", "7480")
                assimilis_port = os.environ.get("HERMES_WEBUI_PORT", "8642")
                env.update({
                    "DEV_MODE": "true",
                    "VIGIL_CSRF_ENABLED": "false",
                    "VIGIL_CONTEXT_PATH": "",
                    "AGENT_INTERNAL_TOKEN": os.environ.get("AGENT_INTERNAL_TOKEN", "chappa-v2-local-vigil-agent-token"),
                    "POSTGRES_HOST": PG_HOST,
                    "POSTGRES_PORT": str(PG_PORT),
                    "POSTGRES_DB": PG_DB,
                    "POSTGRES_USER": PG_USER,
                    "POSTGRES_PASSWORD": PG_PASSWORD,
                    "REDIS_HOST": REDIS_HOST,
                    "REDIS_PORT": str(REDIS_PORT),
                    "REDIS_URL": f"redis://{REDIS_HOST}:{REDIS_PORT}/0",
                    "VIGIL_CORS_ORIGINS": (
                        f"http://127.0.0.1:{chappa_port},http://localhost:{chappa_port},"
                        f"http://127.0.0.1:{assimilis_port},http://localhost:{assimilis_port},"
                        f"http://127.0.0.1:8787,http://localhost:8787"
                    ),
                })
                self._booting.add("vigil")
                self._errors.pop("vigil", None)
                self._procs["vigil"] = subprocess.Popen(
                    [uvicorn_bin, "services.api.main:app", "--host", VIGIL_HOST, "--port", str(VIGIL_PORT)],
                    cwd=str(VIGIL_DIR),
                    env=env,
                    stdout=log_fp,
                    stderr=subprocess.STDOUT,
                )

        if wait_seconds > 0:
            deadline = time.time() + wait_seconds
            while time.time() < deadline:
                if _http_ok(f"{VIGIL_URL}/api/health", timeout=0.6):
                    self._booting.discard("vigil")
                    self._emit_change()
                    return True
                proc = self._procs.get("vigil")
                if proc and proc.poll() is not None:
                    self._booting.discard("vigil")
                    self._errors["vigil"] = f"Vigil exited with code {proc.returncode} (see {LOGS_DIR / 'vigil.log'})"
                    self._emit_change()
                    return False
                time.sleep(0.35)
        return _http_ok(f"{VIGIL_URL}/api/health", timeout=0.5)

    def start_godseye(self, wait_seconds: float = 0.0) -> bool:
        if _http_ok(f"{GODSEYE_URL}/?embed=1", timeout=0.6):
            self._errors.pop("godseye", None)
            return True
        if not (GODSEYE_DIR / "dist" / "index.html").is_file():
            self._errors["godseye"] = "apps/gods-eye-view/dist not built — run ./setup.sh"
            return False
        cmd = _godseye_vite_cmd()
        if not cmd:
            self._errors["godseye"] = "Node/Vite not found — run ./setup.sh"
            return False

        with self._lock:
            existing = self._procs.get("godseye")
            if existing and existing.poll() is None:
                pass
            else:
                LOGS_DIR.mkdir(parents=True, exist_ok=True)
                log_fp = open(LOGS_DIR / "godseye.log", "ab")
                self._logs["godseye"] = log_fp
                env = os.environ.copy()
                env.update({
                    "GEV_EMBED_FRAME_ANCESTORS": "*",
                    "HOST": GODSEYE_HOST,
                    "PORT": str(GODSEYE_PORT),
                })
                self._booting.add("godseye")
                self._errors.pop("godseye", None)
                self._procs["godseye"] = subprocess.Popen(
                    cmd,
                    cwd=str(GODSEYE_DIR),
                    env=env,
                    stdout=log_fp,
                    stderr=subprocess.STDOUT,
                )

        if wait_seconds > 0:
            deadline = time.time() + wait_seconds
            while time.time() < deadline:
                if _http_ok(f"{GODSEYE_URL}/?embed=1", timeout=0.6):
                    self._booting.discard("godseye")
                    self._emit_change()
                    return True
                proc = self._procs.get("godseye")
                if proc and proc.poll() is not None:
                    self._booting.discard("godseye")
                    self._errors["godseye"] = f"God's Eye View exited with code {proc.returncode}"
                    self._emit_change()
                    return False
                time.sleep(0.25)
        return _http_ok(f"{GODSEYE_URL}/?embed=1", timeout=0.5)

    def stop_service(self, name: str) -> dict[str, Any]:
        with self._lock:
            proc = self._procs.pop(name, None)
            log_fp = self._logs.pop(name, None)
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
        if log_fp:
            try:
                log_fp.close()
            except Exception:
                pass
        self._booting.discard(name)
        self._emit_change()
        return self.status()

    def start_service(self, name: str) -> dict[str, Any]:
        if name == "vigil":
            threading.Thread(target=self.start_vigil, kwargs={"wait_seconds": 30.0}, daemon=True).start()
        elif name == "godseye":
            threading.Thread(target=self.start_godseye, kwargs={"wait_seconds": 15.0}, daemon=True).start()
        elif name == "postgres":
            self.ensure_postgres()
        elif name == "redis":
            self.ensure_redis()
        elif name == "all":
            self.start_all_async(self._on_change)
        return self.status()

    def start_all_async(self, on_change: Callable[[dict[str, Any]], None] | None = None) -> None:
        if on_change is not None:
            self._on_change = on_change
        if os.environ.get("CHAPPA_AUTO_START_APPS", "1").strip().lower() in ("0", "false", "no"):
            return

        def _boot_godseye() -> None:
            self.start_godseye(wait_seconds=18.0)
            self._emit_change()

        def _boot_vigil() -> None:
            self.start_vigil(wait_seconds=35.0)
            self._emit_change()

        threading.Thread(target=_boot_godseye, name="chappa-boot-godseye", daemon=True).start()
        threading.Thread(target=_boot_vigil, name="chappa-boot-vigil", daemon=True).start()

    def shutdown_children(self) -> None:
        for name in list(self._procs.keys()):
            try:
                self.stop_service(name)
            except Exception:
                pass

    def status(self) -> dict[str, Any]:
        pg_live = _tcp_open(PG_HOST, PG_PORT, timeout=0.15)
        redis_live = _tcp_open(REDIS_HOST, REDIS_PORT, timeout=0.15)
        vigil_live = _http_ok(f"{VIGIL_URL}/api/health", timeout=0.35)
        godseye_live = _http_ok(f"{GODSEYE_URL}/?embed=1", timeout=0.35)
        if vigil_live:
            self._booting.discard("vigil")
        if godseye_live:
            self._booting.discard("godseye")
        return {
            "postgres": {
                "live": pg_live,
                "host": PG_HOST,
                "port": PG_PORT,
                "db": PG_DB,
                "error": "" if pg_live else self._errors.get("postgres", ""),
            },
            "redis": {
                "live": redis_live,
                "host": REDIS_HOST,
                "port": REDIS_PORT,
                "error": "" if redis_live else self._errors.get("redis", ""),
            },
            "vigil": {
                "live": vigil_live,
                "booting": "vigil" in self._booting and not vigil_live,
                "installed": (VIGIL_DIR / "services" / "api" / "main.py").is_file(),
                "built": (VIGIL_DIR / "clients" / "web" / "build" / "index.html").is_file(),
                "url": VIGIL_URL,
                "mount": "vigil/",
                "mode": "full-vigil-soc" if vigil_live else ("booting" if "vigil" in self._booting else "offline"),
                "error": "" if vigil_live else self._errors.get("vigil", ""),
            },
            "godseye": {
                "live": godseye_live,
                "booting": "godseye" in self._booting and not godseye_live,
                "installed": (GODSEYE_DIR / "package.json").is_file(),
                "built": (GODSEYE_DIR / "dist" / "index.html").is_file(),
                "url": GODSEYE_URL,
                "mount": "godseye/?embed=1",
                "mode": "full-cesium-globe" if godseye_live else ("booting" if "godseye" in self._booting else "offline"),
                "error": "" if godseye_live else self._errors.get("godseye", ""),
            },
        }


MANAGER = RuntimeManager()
