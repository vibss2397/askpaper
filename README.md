# paper-agent

Interactive research paper agent — ask questions, build knowledge, compound insights.

Ingest papers from URLs or PDFs, ask questions grounded in your paper vault, and synthesize what you've learned across papers into knowledge maps and open questions.

## Features

- **Ingest** — import papers from a URL or local PDF; converted to markdown and stored in a vault of spaces
- **Ask** — streaming Q&A grounded in your ingested papers, with context from selected text / source app
- **Summarize** — distill Q&A insights into a per-paper reading summary
- **Synthesize / Knowledge** — find cross-paper connections and build a knowledge map per space
- **Open questions** — curate prioritized knowledge gaps from your reading history
- **Daemon + API** — FastAPI server with SSE streaming (`paper-agent serve`)
- **Raycast extension** — select text anywhere, hit a hotkey, ask (`raycast-extensions/paper-agent`)

## Setup

Requires Python 3.11+.

```bash
pip install -e .
cp .env.example .env   # then fill in your API keys
```

Environment variables (see `.env.example`):

| Variable | Purpose |
|---|---|
| `OPENROUTER_API_KEY` | LLM access via OpenRouter |
| `GLM5.2_key` | GLM provider key |
| `PAPER_AGENT_SECRET` | secret for destructive commands (purge/delete) |

## Usage

```bash
paper-agent init --space ml-research      # create vault + space
paper-agent status                       # vault, spaces, provider/model
paper-agent ingest --space ml-research --url <paper-url>
paper-agent ingest --space ml-research --pdf-path <file.pdf>
paper-agent ask "What is the core contribution?" --space ml-research
paper-agent summarize --space ml-research --paper <paper-id>
paper-agent synthesize --space ml-research
paper-agent knowledge --space ml-research
paper-agent open-questions --space ml-research
paper-agent serve --port 8000            # start daemon/API
```

## Project layout

```
paper_agent/           # core package (agent, ingestion, llm, api, session, vault)
raycast-extensions/    # Raycast UI extension
outputs.md             # working notes
phase-plan.md          # phase plan / roadmap
```
