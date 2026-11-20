# askpaper

Interactive research paper agent — ask questions, build knowledge, compound insights.

Ingest papers from URLs or PDFs, ask questions grounded in your paper vault, and synthesize what you've learned across papers into knowledge maps and open questions.

## How it works

```
PaperAgent.app (menu-bar panel, hotkey ⌃A)  ─┐
Browser / PWA  (http://localhost:8765/app)  ─┤→ daemon (FastAPI, 127.0.0.1:8765) → LLM via OpenRouter
CLI  (paper-agent …)                        ┘        └→ ~/.paper-vault/ (markdown) ← Obsidian
```

- **Panel app** (primary UI): select text anywhere, press the hotkey — your
  selection + source app/URL are captured natively, the panel opens top-center
  with the quote, the continue/fresh thread state, and a streaming answer that
  is auto-saved to the vault.
- **Daemon**: FastAPI + SSE, bound to localhost only. Runs as a user LaunchAgent
  that the panel starts on launch (nothing runs at boot until then); launchd
  keeps it alive and restarts it if it crashes.
- **Vault**: plain markdown on disk — papers, reading sessions, summaries,
  knowledge maps — fully Obsidian-compatible and human-readable.
- **LLM**: any OpenRouter model, set in the vault's `config.yaml`.

## Current functionality

- **Ingest** — arXiv/blog URLs or local PDFs, converted to markdown; unknown
  URLs are auto-ingested mid-ask
- **Ask with context** — paper resolved server-side from the captured URL;
  per-paper conversation threads with section matching (continue vs fresh);
  paper override picker; cross-space retargeting
- **Capture ladder** — AX selected text → browser JS selection → arXiv-ID
  from window title → clipboard fallback (browser/PDF apps only, clipboard
  restored intact afterwards)
- **Summaries** — per-paper reading summaries with staleness tracking
  (new Q&A since last summary is flagged)
- **Synthesize / knowledge / open questions** — cross-paper connections,
  knowledge map, curated open questions per space
- **Session history** — every Q&A saved to dated markdown in the vault
- **CLI** — every operation available as `paper-agent <command>`
- **Health** — versioned `/api/health` (version + pid + API-key presence);
  menu-bar dot: green = daemon up, gray = down

## Setup

Requires Python 3.11+ (uv manages the venv automatically).

```bash
make setup            # .venv + dependencies
cp .env.example .env  # then fill in your API keys
```

Environment variables (see `.env.example`):

| Variable | Purpose |
|---|---|
| `OPENROUTER_API_KEY` | LLM access via OpenRouter |
| `PAPER_AGENT_SECRET` | secret for destructive commands (purge/delete) |

## Running

**Daemon as a service (recommended)** — install once:

```bash
make daemon-install   # LaunchAgent; panel starts it, launchd keeps it alive
```

**Panel app** (build requires only Command Line Tools, no Xcode license):

```bash
cd paper-agent-swift-app/PaperAgent
./build.sh
open build/PaperAgent.app
```

- `●` appears in the menu bar — green = daemon reachable, gray = down
- Press **⌃A** anywhere to open the panel with your selection; hotkey is
  changeable in the menu bar's "Hotkey" submenu
- First use triggers macOS permission prompts (Accessibility; per-browser
  Automation) — approve them in System Settings when asked

**Manually** (from the repo root, or `.env` won't be found):

```bash
uv run paper-agent serve --port 8765
```

**Browser fallback** — the same UI runs at `http://localhost:8765/app`
(works as an installable PWA in Chrome).

## CLI usage

```bash
paper-agent init --space ml-research      # create vault + space
paper-agent status                        # vault, spaces, provider/model
paper-agent ingest --space ml-research --url <paper-url>
paper-agent ingest --space ml-research --pdf-path <file.pdf>
paper-agent ask "What is the core contribution?" --space ml-research
paper-agent summarize --space ml-research --paper <paper-id>
paper-agent synthesize --space ml-research
paper-agent knowledge --space ml-research
paper-agent open-questions --space ml-research
paper-agent serve --port 8765             # start daemon/API
```

## Tests

```bash
make test   # pytest API contract suite — tmp vault, no network, no real .env
```

## Project layout

```
paper_agent/           # core package (agent, ingestion, llm, api, session, vault, daemon)
paper_agent/webapp/    # panel web page served by the daemon at /app
paper-agent-swift-app/ # native macOS panel app (primary UI)
tests/                 # pytest API contract tests
Makefile               # setup / daemon-install / test / run
outputs.md             # working notes (historical log)
phase-plan.md          # phase plan / roadmap (historical)
paper-agent-swift-app/migration_plan.md  # Swift migration plan (historical)
```

## Next steps

1. **Prompt tuning (9.1)** — quality pass over the ask/summarize/synthesize
   prompts; the pytest suite guards the API contract while prompts change
2. **Space control plane (9.6)** — create/manage spaces from the web page
3. **Remote access** — expose the daemon to phone/iPad via Tailscale Serve +
   a mobile CSS pass (PWA already works over HTTPS)
4. **Later phases** — multimodal asks (10), MCP adapter (11), WhatsApp bridge
   (12), iPad (13), voice input (14); search (8) stays deferred
