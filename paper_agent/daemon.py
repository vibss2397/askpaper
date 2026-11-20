"""Daemon lifecycle: run the API server, probe for an already-running
instance, and install/uninstall a per-user LaunchAgent so the daemon
starts at login and restarts if it crashes."""

import json
import logging
import os
import plistlib
import subprocess
import time
import urllib.request
from logging.handlers import RotatingFileHandler
from pathlib import Path

import uvicorn

DEFAULT_PORT = 8765
APP_VERSION = "0.1.0"
LAUNCH_LABEL = "com.vibhu.paperagent.daemon"
LOG_DIR = Path.home() / "Library" / "Logs" / "paper-agent"

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _git_sha() -> str:
    """Best-effort git short SHA so a stale daemon is identifiable (§stale-daemon gotcha)."""
    try:
        out = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=2,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return ""


_GIT_SHA = _git_sha()


def full_version() -> str:
    return f"{APP_VERSION}+{_GIT_SHA}" if _GIT_SHA else APP_VERSION


def health_payload() -> dict:
    return {"status": "ok", "version": full_version(), "pid": os.getpid()}


def probe_running(port: int, timeout: float = 1.0) -> dict | None:
    """Health JSON of an already-running paper-agent daemon on this port, else None.
    Requires both the status and version keys so a foreign service on the port
    is not mistaken for our daemon."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=timeout) as res:
            data = json.loads(res.read().decode())
            if isinstance(data, dict) and data.get("status") == "ok" and "version" in data:
                return data
    except Exception:
        pass
    return None


def run(port: int = DEFAULT_PORT, reload: bool = False, log_file: str | None = None):
    existing = probe_running(port)
    if existing:
        print(
            f"paper-agent daemon already running on port {port} "
            f"(pid {existing.get('pid', '?')}, v{existing.get('version', '?')}) — nothing to do. "
            f"Kill it first if you want a fresh start: kill {existing.get('pid', '<pid>')}"
        )
        return

    if log_file:
        # Rotated file for the app's (redacted) logs. log_config=None keeps
        # uvicorn's loggers unconfigured so they propagate to root and land
        # here too, instead of uvicorn configuring its own stderr handlers.
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logging.getLogger().addHandler(handler)

    print(f"paper-agent running on http://localhost:{port} (v{full_version()})")
    uvicorn.run(
        "paper_agent.api.server:app",
        host="127.0.0.1",
        port=port,
        reload=reload,
        log_config=None,
        log_level="info",
    )


# ── LaunchAgent (run at login, restart on crash) ────────────────────────────

def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_LABEL}.plist"


def _venv_binary() -> Path:
    return _REPO_ROOT / ".venv" / "bin" / "paper-agent"


def install_launchagent(port: int = DEFAULT_PORT) -> None:
    """Write the LaunchAgent plist and bootstrap it into the current GUI session.

    The agent is registered but NOT started at login (no RunAtLoad): the panel
    app kickstarts it on launch, and KeepAlive keeps it running afterwards."""
    binary = _venv_binary()
    if not binary.exists():
        raise SystemExit(f"venv binary not found at {binary} — run `make setup` first")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    app_log = LOG_DIR / "daemon.log"
    out_log = LOG_DIR / "daemon.out.log"

    existing = probe_running(port)
    if existing:
        raise SystemExit(
            f"a daemon is already running on port {port} (pid {existing.get('pid', '?')}, "
            f"v{existing.get('version', '?')}) — kill it first, then re-run: "
            f"kill {existing.get('pid', '<pid>')}"
        )

    plist = {
        "Label": LAUNCH_LABEL,
        "ProgramArguments": [
            str(binary), "serve",
            "--port", str(port),
            "--log-file", str(app_log),
        ],
        "WorkingDirectory": str(_REPO_ROOT),  # .env discovery via cwd
        # No RunAtLoad: the daemon starts when the panel app kickstarts it on
        # launch (user preference — nothing runs until the app is opened).
        # KeepAlive keeps it alive/restarts it on crash from then on.
        "KeepAlive": True,
        "ProcessType": "Background",
        "StandardOutPath": str(out_log),
        "StandardErrPath": str(out_log),
    }
    plist_path = _plist_path()
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_bytes(plistlib.dumps(plist))

    uid = os.getuid()
    target = f"gui/{uid}"
    subprocess.run(["launchctl", "bootout", target, str(plist_path)], capture_output=True)
    subprocess.run(["launchctl", "bootstrap", target, str(plist_path)], check=True)

    # Wait for the daemon to come up; bootstrap without RunAtLoad doesn't start
    # it, so kickstart once ourselves — this also verifies the service works.
    subprocess.run(["launchctl", "kickstart", f"{target}/{LAUNCH_LABEL}"], capture_output=True)
    for _ in range(60):
        if probe_running(port):
            print(f"daemon installed and running (v{full_version()})")
            print(f"  plist:     {plist_path}")
            print(f"  logs:      {app_log} (rotated) + {out_log}")
            print(f"  starts when the panel app opens it (not at login); "
                  f"restart with: launchctl kickstart -k {target}/{LAUNCH_LABEL}")
            return
        time.sleep(0.5)
    print(f"daemon installed but not answering on :{port} yet — check {out_log}")


def uninstall_launchagent() -> None:
    plist_path = _plist_path()
    subprocess.run(
        ["launchctl", "bootout", f"gui/{os.getuid()}", str(plist_path)],
        capture_output=True,
    )
    if plist_path.exists():
        plist_path.unlink()
    print("daemon LaunchAgent removed (a manually started daemon, if any, is untouched)")
