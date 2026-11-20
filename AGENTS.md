# AGENTS.md

Instructions for AI coding agents working in this repository.

## Security

- **Never read, print, or log the `.env` file or its contents.** Treat it as off-limits. Use `.env.example` as the reference for variable names only.

## Environment

- Python deps are managed with **uv**.
- Tests: `make test` (pytest over FastAPI TestClient — tmp vault via `PAPER_AGENT_VAULT`, no network, no real .env). Run after touching the API, vault, or session code.
- First-time setup: `make setup` (creates `.venv` with uv, syncs Python deps, runs `bun install`).
- Python venv lives at `.venv/` in the repo root — activate with `source .venv/bin/activate`, or run without activating via `uv run <cmd>` / `make run CMD="..."`.
- Python 3.11 is required; uv downloads and manages it automatically.
- The system `python3` (Apple's 3.9) is not used for this project.

## Running

- CLI: `uv run paper-agent <command>` (see README for commands).
- Daemon/API: `uv run paper-agent serve --port 8765` — **always from the repo root** (it discovers `.env` via cwd). Both UIs talk to it at `http://localhost:8765`. Check `lsof -nP -iTCP:8765` for a stale daemon when behavior seems off (health now reports version+pid, so the panel menu identifies a stale daemon; `serve` is idempotent — it refuses to double-start).
- Daemon as a service (installed): `make daemon-install` sets up a LaunchAgent (`com.vibhu.paperagent.daemon`, **no RunAtLoad**). The Swift panel kickstarts it on launch, and `KeepAlive` keeps/restarts it from then on — so after a reboot the daemon only comes up when the panel is first opened (remote/phone access requires panel-open-since-boot). Logs at `~/Library/Logs/paper-agent/daemon.log` (`make daemon-log`). `make daemon-uninstall` removes it. A manually-started daemon blocks install (kill it first).
- Web page (browser/PWA fallback UI): `http://localhost:8765/app`.
- Swift panel app (primary + only UI): `paper-agent-swift-app/PaperAgent/build.sh` then `open paper-agent-swift-app/PaperAgent/build/PaperAgent.app` — builds with CommandLineTools `swiftc`, no Xcode license needed. Hotkey configurable via the menu-bar "Hotkey" submenu (presets in `HotkeyCenter.swift`, default ⌃A, persisted in UserDefaults; ⌘⇧P is also available now that Raycast is gone). See `paper-agent-swift-app/migration_plan.md` before touching Swift code (esp. §6.5/§7: WKWebView gotchas, App Nap assertion must stay).
- The Raycast extension was deleted at cutover (source removed from the repo; removed from the Raycast app). It lives on in git history if a fallback UI is ever needed.

## Project layout

- `paper_agent/` — core Python package (agent, ingestion, llm, api, session, vault).
- `paper_agent/webapp/` — the web page served by the daemon at `/app` (vanilla JS, no build step; also hosted inside the Swift panel's WKWebView).
- `paper-agent-swift-app/` — native macOS panel app (Xcode project + `build.sh`; `migration_plan.md` is its source of truth).
