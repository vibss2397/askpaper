# paper-agent — Phased Build Plan (Revised)

## Architecture (final state)

```
PaperAgent.app (Swift menu-bar panel, ⌘⌃⇧A → ⌘⇧P at cutover) ──▶ paper-agent daemon (HTTP/SSE) ──▶ ~/.paper-vault/ ──▶ Obsidian
Raycast (fallback until Phase 6 cutover, then unbound) ───────▶        ├─ pdf ingestion                  │
WhatsApp──▶                                                            ├─ LLM (OpenRouter — any model)   │
Claude  ──▶ MCP ──▶                                                    ├─ spaces/sessions                │
                                                                       ├─ summaries/cross-paper          │
                                                                       ├─ search                         │
                                                                       └─ vault writer                   │
```

> **UI rewrite status (Oct 2026):** the Raycast extension has been replaced as the primary UI by a
> native Swift panel app — migration Phases 0–4 (daemon additions, web page, Swift skeleton,
> hotkey/capture/handoff parity) are **complete and live-verified**; Raycast remains installed and
> bound to ⌘⇧P as the safety net until the cutover. The migration's single source of truth is
> `paper-agent-swift-app/migration_plan.md`; results + the agreed next-steps order (env key → Safari
> selection capture → Zen decision → Phase 5 polish → Phase 6 cutover → 9.1/9.6 → Phases 10–14) are
> in the "Swift Panel App Migration" section of `outputs.md`. Phase 5 below is now historical (its
> UI is the fallback).

## Vault shape (target)

```
~/.paper-vault/
  spaces/
    ml-research/
      index.md
      knowledge.md
      open-questions.md
      papers/
        attention-is-all-you-need/
          paper.pdf
          paper.md
          metadata.yaml
      sessions/
        2026-05-03-attention.md
      summaries/
        2026-05-03-summary.md
        cross-paper-insights.md
  .paper-agent/
    config.yaml
    index.sqlite
```

---

## Phase 1: Scaffold + Vault + Spaces

**Goal:** `paper-agent` CLI exists. You can create a space. Vault directory tree is created.

### Steps

| Step | Action | Incremental output |
|------|--------|--------------------|
| 1.1 | Leave old `frontend/`, `backend/` directories untouched while building new `paper_agent/` package alongside them | No destructive cleanup; legacy code remains available for reference |
| 1.2 | `pyproject.toml` — deps: `click`, `pyyaml`, `google-genai`, `fastapi`, `uvicorn`, `sse-starlette` | `pip install -e .` works |
| 1.3 | `paper_agent/cli.py` — Click CLI: `init`, `status`, `serve` | `paper-agent --help` prints commands |
| 1.4 | `paper_agent/vault.py` — create `~/.paper-vault/spaces/{name}/` with subdirs on `init` | `paper-agent init ml-research` → vault tree exists |
| 1.5 | `paper_agent/config.py` — load `~/.paper-vault/.paper-agent/config.yaml` (model, vault path, API key from env `GEMINI_API_KEY`) | `paper-agent status` prints: vault path, spaces, model, key configured ✓/✗ |
| 1.6 | `paper_agent/daemon.py` — stub daemon: starts, prints port, holds | `paper-agent serve` stays alive |

### Verify
```bash
paper-agent init ml-research
paper-agent status
# → vault at ~/.paper-vault/
# → space: ml-research
# → model: gemini-2.5-flash
# → API key: ✓

paper-agent serve
# → paper-agent running on http://localhost:8765
```

---

## Phase 2: Ask (No PDF Required)

**Goal:** `paper-agent ask "question" --space ml-research --selected "copied text"` — sends question + selected text + source metadata to Gemini, streams answer. No file ingestion yet. Just the core loop.

### Steps

| Step | Action | Incremental output |
|------|--------|--------------------|
| 2.1 | `paper_agent/llm/gemini.py` — Gemini 2.5 Flash client, `ask(prompt) -> AsyncIterator[str]` | `python -m paper_agent.llm.gemini "hello"` → "Hello! How can I help?" |
| 2.2 | `paper_agent/llm/prompts.py` — prompt templates: system prompt + selected text as context + question | Prompt: "You are a research assistant. The user is reading a paper in space 'ml-research'. Context: [selected text]. Question: [question]" |
| 2.3 | `paper_agent/agent/ask.py` — `ask(space, question, selected_text="", source_metadata={}) -> AsyncIterator[str]` | Streaming text response |
| 2.4 | `paper-agent ask "explain this" --space ml-research --selected "the quick brown fox" --source-app Chrome --source-title "Attention paper" --source-url "https://arxiv.org/..."` — CLI command | **`paper-agent ask "question"`** streams answer in terminal — the core loop works |

### Verify
```bash
paper-agent ask "what is a transformer?" --space ml-research
# → tokens stream: "A transformer is a neural network architecture..."

paper-agent ask "explain this concept" \
  --space ml-research \
  --selected "self-attention computes weighted sums of values" \
  --source-app Chrome \
  --source-title "Attention Is All You Need" \
  --source-url "https://arxiv.org/abs/1706.03762"
# → tokens stream with context-aware answer
```

---

## Phase 3: Session Persistence

**Goal:** Every Q&A auto-saved to a dated session file in the vault. Open Obsidian → see your conversation history.

### Steps

| Step | Action | Incremental output |
|------|--------|--------------------|
| 3.1 | `paper_agent/session/writer.py` — `save_qa(space, question, answer, selected_text, source_metadata)` → appends to `sessions/YYYY-MM-DD.md` inside the space | Daily session file created with YAML frontmatter |
| 3.2 | Session file format: `---` frontmatter (space, model, date) + `## Q&A` section with numbered entries + selected text context + source metadata | Q&A entries formatted: `### Q1`, `**Q:**`, `**Source:**`, `**Context:**`, `**A:**` |
| 3.3 | Wire into `ask()`: after streaming completes, auto-save Q&A | CLI ask: answer streams, then "Saved to ml-research/2026-05-03 session" |
| 3.4 | `paper_agent/session/reader.py` — `get_history(space, n=5)` → returns last N Q&A pairs | Used later for `/append` in Raycast |
| 3.5 | Space `index.md` — auto-creates with list of sessions + timestamps | Open Obsidian: `spaces/ml-research/index.md` shows recent activity |
| 3.6 | `paper_agent/context.py` — stores lightweight active context: `last_space`, `last_source_url`, `last_source_title`, `active_paper_id` | Raycast can default intelligently without extra clicks |

### Verify
```bash
paper-agent ask "explain attention" --space ml-research --selected "Scaled Dot-Product Attention"
# → streaming answer
# → "Saved to ml-research session 2026-05-03"

cat ~/.paper-vault/spaces/ml-research/sessions/2026-05-03.md
# → Q&A entry preserved

# Open Obsidian on ~/.paper-vault/
# → See index.md → click session file → Q&A history
```

---

## Phase 4: Minimal Daemon API (HTTP + SSE)

**Goal:** Daemon exposes REST API. `curl`-able. Ready for Raycast. SSE for streaming (simpler than WebSocket for Raycast).

### Steps

| Step | Action | Incremental output |
|------|--------|--------------------|
| 4.1 | `paper_agent/api/server.py` — FastAPI app, CORS for localhost, starts on `paper-agent serve` | `http://localhost:8765` alive |
| 4.2 | `GET /api/spaces` — list spaces with name + session count | `curl localhost:8765/api/spaces` → `[{name: "ml-research", sessions: 3}]` |
| 4.3 | `POST /api/spaces/{name}/ask` — JSON body: `{question, selected_text, source_app, source_title, source_url, paper_id?}`. Returns SSE stream of text tokens. | `curl -X POST .../api/spaces/ml-research/ask -d '{"question":"what is attention?"}'` → SSE token stream |
| 4.4 | `GET /api/spaces/{name}/sessions` — list session files with dates + question counts | Session list API |
| 4.5 | `GET /api/spaces/{name}/sessions/{date}` — get full session content as JSON | Single session read |
| 4.6 | `GET /api/context` + `PUT /api/context` — read/update active context (`last_space`, `active_paper_id`, recent source metadata) | Raycast defaults to the right space/source/paper |

### Verify
```bash
paper-agent serve

curl localhost:8765/api/spaces
# → [{"name": "ml-research", "sessions": 1}]

curl -N -X POST localhost:8765/api/spaces/ml-research/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "explain self-attention", "selected_text": "Attention(Q,K,V) = softmax(QK^T/√dk)V", "source_app": "Chrome", "source_title": "Attention Is All You Need", "source_url": "https://arxiv.org/abs/1706.03762"}'
# → data: Self
# → data: -attention
# → data: computes...
```

---

## Phase 5: Raycast Hotkey (The Magic)

**Goal:** Select text in any app → Cmd+Shift+P → space dropdown → question → streamed answer. The real product. No PDF ingestion needed yet.

### Steps

| Step | Action | Incremental output |
|------|--------|--------------------|
| 5.1 | Init Raycast extension project: `raycast-extensions/paper-agent/` with `package.json`, `tsconfig.json` | `npm run dev` opens in Raycast |
| 5.2 | `src/ask.tsx` — main command: reads selected text from active app (via AppleScript/clipboard), captures app/browser title/URL when available, fetches spaces from `GET /api/spaces`, renders dropdown + text input | Hotkey → Raycast window with "ml-research" in dropdown |
| 5.3 | Space dropdown: defaults from daemon active context, then Raycast `LocalStorage`, then configured default | One less click each time |
| 5.4 | Submit → `POST /api/spaces/{name}/ask` with `{question, selected_text, source_app, source_title, source_url}` via fetch + ReadableStream. Render markdown tokens as they arrive. | Question submitted → streaming markdown in Raycast detail view |
| 5.5 | `src/session-history.tsx` — browse past sessions in Raycast, click to open in Obsidian or read inline | Quick lookup of past Q&A |
| 5.6 | Extension preferences: daemon URL, default space, hotkey | Configurable in Raycast prefs |

### Verify
```
1. paper-agent serve (local)
2. Open Chrome → navigate to arxiv paper → select a paragraph
3. Cmd+Shift+P → Raycast opens
4. Dropdown shows "ml-research" (last used)
5. Type "explain this concept"
6. Press Enter
7. Streaming markdown response renders inline in Raycast
8. Session auto-saved to vault

Daily loop: select → hotkey → type → read answer → repeat
```

---

## Phase 6: PDF Ingestion ✅ Done

**Goal:** Add a paper PDF → converted to markdown → saved to vault → available as full context when selected via `paper_id` or auto-detected from `source_url`. Now answers get *much* better without injecting every paper in a space.

### What was built

```
paper_agent/
  ingestion/
    __init__.py
    pdf_converter.py     # pymupdf4llm: PDF → (markdown, title). Title extracted from first H1 in markdown.
    fallback.py          # Gemini Vision: scanned PDF → markdown. Batched 10 pages/request at 150 DPI.
                         #   Triggered when pymupdf4llm output <100 chars. Configurable via config.yaml.
    html_extractor.py    # trafilatura + httpx: URL → (markdown, title). Handles blogs, articles, docs.
    downloader.py        # httpx async download. arxiv abs→pdf URL normalization. Content-type detection (PDF vs HTML).
    pipeline.py          # ingest(space, source) → orchestrates download → convert/extract → fallback → save to vault.
                         #   find_paper_by_url(space, url) → checks metadata.yaml for matching source_url or arxiv ID.
  vault.py               # + list_papers(), get_paper_path(), get_paper_metadata(), purge_space(), delete_space()
  config.py              # + get_secret_key() for PAPER_AGENT_SECRET env var
  llm/prompts.py         # + paper_content/paper_title params in build_user_prompt()
  agent/ask.py           # + paper_id param, auto-ingestion from source_url, paper.md injection into prompt
  api/server.py          # + POST /api/spaces/{name}/papers (URL or file upload), GET /api/spaces/{name}/papers
                         #   + DELETE /api/spaces/{name}/contents (purge), DELETE /api/spaces/{name} (delete space)
                         #   Wired body.paper_id → run_ask()
  cli.py                 # + paper-agent ingest --space <name> [--url URL | <pdf_path>]
                         #   + --paper flag on ask command
                         #   + paper-agent purge --space <name> --secret <key>
                         #   + paper-agent delete-space --space <name> --secret <key>
raycast-extensions/paper-agent/src/
  ask.tsx                # + Paper dropdown (populated from GET /api/spaces/{name}/papers)
                         #   + Ingestion status events in SSE stream (ingesting/ingested/ingest_failed)
                         #   + paper_id passed in POST ask body
```

### Key decisions

- **Library choice: pymupdf4llm** (not docling/marker) — lightweight (~50MB), sub-second conversion, serverless-friendly. Built-in Tesseract OCR for partially scanned pages. Gemini Vision fallback for truly scanned PDFs (~$0.05/60pg, rare).
- **No PDF stored in vault** — only `paper.md` + `metadata.yaml`. The PDF is a temp file during conversion, deleted after. `source_url` in metadata allows re-download if needed.
- **Auto-ingestion in ask flow** — no separate hotkey. When `source_url` is provided and no paper is cached for that URL, the daemon auto-downloads and converts before answering. Status events (`{"status": "ingesting"}`, `{"status": "ingested"}`) flow through SSE stream to Raycast.
- **URL-based ingestion** — arxiv abs→pdf URL normalization (`arxiv.org/abs/XXXX` → `arxiv.org/pdf/XXXX`). HTML pages extracted via trafilatura (blogs, articles, docs). Twitter deferred.
- **Paper slug from title** — extracted from first H1 heading in converted markdown, then slugified. Zero cost, instant. Falls back to filename if title extraction fails.
- **Full paper context** — entire `paper.md` injected into prompt. No truncation or chunking. Gemini 2.5 Flash has 1M token context. Smart context selection deferred to Phase 9.
- **Explicit paper selection** — ask() requires `paper_id` or `source_url` to use paper context. No silent fallback to `active_paper_id`. If neither is provided, answer is selected-text-only.
- **Secret-protected destructive operations** — `purge` and `delete-space` require `PAPER_AGENT_SECRET` from `.env`. API uses `X-Paper-Agent-Secret` header. `delete-space` refuses if space is non-empty (purge first).
- **Dependencies added:** pymupdf4llm, python-multipart, httpx, trafilatura, lxml_html_clean

### Vault shape (updated)

```
~/.paper-vault/
  spaces/
    {name}/
      papers/
        {paper-slug}/
          paper.md          # converted markdown (the only content file)
          metadata.yaml     # title, source_url, type (pdf|html), ingested_at, page_count, conversion_method
      sessions/
      summaries/
```

### API endpoints (updated)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/spaces/{name}/papers` | List papers with metadata |
| `POST` | `/api/spaces/{name}/papers` | Ingest from `{url}` JSON or multipart file upload |
| `DELETE` | `/api/spaces/{name}/contents` | Purge all space contents (requires secret) |
| `DELETE` | `/api/spaces/{name}` | Delete space — only if empty (requires secret) |

### Verified

```
# CLI ingest from URL
paper-agent ingest --space research --url https://arxiv.org/abs/1706.03762
# → "Ingested: Attention Is All You Need" (15 pages, pymupdf4llm)

# CLI ingest from local file
paper-agent ingest --space research ~/Downloads/paper.pdf
# → "Ingested: Eagle: Efficient Training-Free Router..." (8 pages)

# CLI ask with explicit paper
paper-agent ask "what is the key innovation?" --space research --paper attention-is-all-you-need
# → Answer grounded in full 15-page paper

# CLI ask with auto-find from URL (cached paper)
paper-agent ask "what is attention?" --space research --source-url https://arxiv.org/abs/1706.03762
# → Finds cached paper → answer grounded in full paper

# CLI ask with auto-ingestion (new URL)
paper-agent ask "what is this paper about?" --space research --source-url https://arxiv.org/abs/2409.15518
# → [Downloading and converting paper...]
# → [ingested]
# → Answer grounded in full Eagle paper

# API ingest from URL
curl -X POST localhost:8765/api/spaces/research/papers -d 'url=https://arxiv.org/abs/1706.03762'
# → {"title":"Attention Is All You Need","slug":"attention-is-all-you-need",...}

# API ingest from file upload
curl -X POST localhost:8765/api/spaces/research/papers -F file=@paper.pdf
# → {"title":"Eagle: ...","slug":"eagle-...",...}

# API list papers
curl localhost:8765/api/spaces/research/papers
# → [{paper_id, title, type, source_url, ingested_at, page_count, conversion_method}, ...]

# API purge (secret-protected)
curl -X DELETE localhost:8765/api/spaces/research/contents -H "X-Paper-Agent-Secret: <key>"
# → {"status":"ok","purged":{"papers":4,"sessions":3,"summaries":0}}

# API delete space (secret-protected, only if empty)
curl -X DELETE localhost:8765/api/spaces/research -H "X-Paper-Agent-Secret: <key>"
# → {"status":"ok"}

# HTML ingestion (blog post)
paper-agent ingest --space research --url https://lilianweng.github.io/posts/2023-03-15-prompt-engineering/
# → "Ingested: Prompt Engineering" (html, trafilatura)

# Raycast
npx tsc --noEmit                         ✓ (0 errors)
npm run build                            ✓ (3 entry points compiled)
```

### Notes for next phase (Phase 7)

- Phase 7 needs: paper summaries, `knowledge.md`, cross-paper synthesis
- `paper.md` is available for Gemini to read and summarize
- `metadata.yaml` has all paper metadata for indexing
- Session files have Q&A history that can feed into summaries
- API endpoints to add: `POST /api/spaces/{name}/summarize`, `POST /api/spaces/{name}/synthesize`

---

## Phase 7: Summaries + Knowledge Compounding ✅ Done

**Goal:** Agent generates paper summaries, space-level knowledge, and cross-paper insights. Knowledge grows over time.

### Steps

| Step | Action | Incremental output |
|------|--------|--------------------|
| 7.1 | `paper-agent summarize --space ml-research --paper attention-is-all-you-need` — Gemini reads paper.md + all sessions → writes structured summary (contributions, methodology, findings, open questions) | `papers/.../summary.md` populated |
| 7.2 | Space `knowledge.md` — agent reads all summaries + sessions → writes "what this space knows" | `spaces/ml-research/knowledge.md` evolves each session |
| 7.3 | Space `open-questions.md` — agent extracts unanswered/follow-up questions from all Q&A | Running list of things to revisit |
| 7.4 | `paper-agent synthesize --space ml-research` — cross-paper insights: reads all summaries → finds connections, contradictions, themes across papers | `spaces/ml-research/summaries/cross-paper-insights.md` |
| 7.5 | `POST /api/spaces/{name}/summarize` — API endpoint, triggerable from Raycast | Raycast "Summarize this paper" command |
| 7.6 | Space `index.md` enhancements — links to all papers, sessions, summaries, knowledge.md, open-questions.md | Open Obsidian → space index is your dashboard |

### Verify
```bash
paper-agent summarize --space ml-research --paper attention-is-all-you-need
# → Summary written

cat ~/.paper-vault/spaces/ml-research/papers/attention-is-all-you-need/summary.md
# → Agent-written summary: "Key contribution: Transformer architecture eliminates recurrence..."

paper-agent synthesize --space ml-research
# → Cross-paper insights generated

# Open Obsidian → knowledge.md has grown, cross-paper links visible in graph view
```

---

## Phase 9: Desktop Polish (Partial ✅ — 9.4 + 9.5 + 9.7 done)

**Goal:** Perfect the desktop experience before building any external integrations. These are quality-of-life improvements that make the daily loop smoother and more powerful. 9.4 (loop mode / reading sessions) and 9.5 (conversation continuity) are done; 9.7 (LLM provider abstraction via OpenRouter — unplanned, emerged from wanting luna as a model option) also shipped. 9.1 and 9.6 remain (design notes below), 9.2 dropped, 9.3 covered.

### What was built (9.4 + 9.5)

```
paper_agent/
  agent/
    sections.py           # NEW: parse_sections(paper_markdown) — splits paper.md into sections by heading path (stack-based;
                          #   strips * / _ from pymupdf4llm's "## **bold**" headings; skips code blocks)
                          #   find_section(paper_markdown, selected_text) — locates the selection inside paper.md, returns full
                          #   heading path. normalize() is punctuation-insensitive (strips non-alphanumerics), rejoins hyphenated
                          #   line breaks ("atten-\ntion"), folds Unicode ligatures (ﬁ→fi etc.) + quote/dash variants.
                          #   Tries full selection first, then an 80-char probe from the start. "" on no match.
                          #   deepest(path) — last segment for display ("3.3 Position-wise Feed-Forward Networks")
    ask.py                # Thread decision after paper resolution: current section from selection, last 5 turns
                          #   (THREAD_HISTORY_TURNS = 5) loaded from the reading file, then _should_continue() decides
                          #   follow-up vs fresh. Continuing injects prior Q&A into the prompt as
                          #   "**Earlier in this conversation:**" turns. fresh flag bypasses history (param, POST /ask body
                          #   field, CLI --fresh). Section inheritance when continuing without a section match. No URL + no
                          #   selection → last active paper (global rule, incl. CLI). New pre-token SSE events:
                          #   {"status": "resolved", space, paper} and {"status": "thread", section, continued}.
                          #   Cross-space retarget to the owning space via find_paper_anywhere().
  ingestion/
    pipeline.py           # + find_paper_anywhere(url, prefer_space=None) — cross-space URL lookup → (space, paper_id);
                          #   prefers the requested space on multi-match
  llm/
    prompts.py            # + conversation_history param in build_user_prompt(); system prompt gained a continuity sentence
  session/
    writer.py             # Reading sessions: paper-resolved Q&A appends to ONE file sessions/reading-{paper-slug}.md
                          #   (frontmatter: paper, reading_session: true, started_at, qa_count — updated each append, source_url).
                          #   Each entry stores a **Section:** heading path. Non-paper asks keep the dated-file + AI-slug path;
                          #   the LLM slug-generation call is SKIPPED for reading sessions (one less Gemini call per question).
                          #   + reading_session_path(space, paper_id)
    reader.py             # + section field parsing; get_recent_qa_for_paper(space, paper_id, n) — prefers the reading file,
                          #   falls back to scanning legacy dated files by paper_id; + get_session_by_filename()
  api/
    server.py             # + GET /api/spaces/{name}/session-files/{filename} (path-traversal-guarded) — reading files have no date
                          #   + POST /api/resolve — thread-state preview (no side effects, no LLM)
                          #   + fresh field on POST /ask body
  cli.py                  # + paper-agent ask --fresh
raycast-extensions/paper-agent/src/
  ask.tsx                 # REWRITE: chat-style single window — Composer (Form) ↔ ThreadView (Detail with accumulating transcript
                          #   + streaming answer), no navigation-stack growth. Hotkey always lands on the Composer (WhatsApp-style).
                          #   Thread status line (● continuing §X — N prior Q&A / ○ fresh thread / ○ new paper / ○ no paper),
                          #   History (last 5 Q&A), "Replying to §X" quote. Keys: ⏎ send · ⌘N Force New Thread · ⌘H View Full
                          #   Thread · ⌘R Refresh Selection (re-captures AND re-runs the resolve preview) · ⇧⌘P Change Paper….
                          #   On mount / ⌘R: POST /api/resolve → hydrate space, resolved paper, seed turns from recent_qa.
                          #   Paper dropdown + LS_LAST_PAPER removed — server resolves the paper from the URL; space follows paper.
  session-history.tsx     # Reading files render as "title (reading)" with "ongoing" date, open via the new session-files endpoint
```

### Key decisions

- **One reading file per paper, not per day (9.4):** any ask that resolves to a paper appends to `sessions/reading-{paper-slug}.md` with `reading_session: true` frontmatter (`paper`, `started_at`, `qa_count` incremented per append, `source_url`). Non-paper asks keep the old dated-file + AI-slug path. Automatic per-paper grouping keyed by resolved paper / source_url — NOT a toggle (simpler than the plan's "reading-mode flag"). The LLM slug call is skipped for reading sessions — one less Gemini call per question.
- **Every entry records its section:** a `**Section:**` line with the full heading path (e.g. `Attention Is All You Need > 3 Model Architecture > 3.3 Position-wise Feed-Forward Networks`) — this is what continuity decisions are made on.
- **Section matcher, not fuzzy search:** new `paper_agent/agent/sections.py`. `parse_sections()` walks heading paths with a stack (handling pymupdf4llm's `## **bold**` headings, skipping code blocks); `find_section()` locates the selection via a punctuation-insensitive `normalize()` (strips non-alphanumerics, rejoins hyphenated line breaks, folds Unicode ligatures and quote/dash variants), trying the full selection then an 80-char probe. Known caveat: pymupdf4llm sometimes drops headings into garbled figure text (the Attention paper lost §3.1/§3.2) → matches land on the nearest surviving heading; verbatim selections match, paraphrases don't.
- **Section-based continuation rule:** `_should_continue(current_section, prev_pairs, has_selection)` fallback ladder — no prior turns → fresh; no selection → continue; selection not found in paper.md → continue (same-paper rule); different section → fresh. When continuing, the last 5 turns (`THREAD_HISTORY_TURNS = 5`) are injected into the prompt as "**Earlier in this conversation:**" turns.
- **Section inheritance:** when continuing without a section match (no selection or match failure), the thread inherits the last entry's section — shown in the `thread` SSE event AND stored in the saved entry, so a later same-section selection still continues (the chain doesn't break).
- **The vault IS the conversation state (9.5):** the plan's stateless-vs-stateful open question resolved in favor of stateful server-side — the client sends no `conversation_history`; prior Q&A is loaded from the reading file on each ask.
- **Last-active-paper fallback is global:** no URL + no selection → `context.get_active_paper_id()` (requested space, then `last_space`). Includes the CLI — a bare `paper-agent ask "..."` continues the last paper's thread. Escapes: `--fresh`, any `--selected` text, or `--paper`.
- **Server-resolved paper; space follows paper:** the Raycast Paper dropdown and `LS_LAST_PAPER` were removed entirely — they used to default from LocalStorage/last-active paper and send explicit `paper_id`, silently OVERRIDING URL-based resolution (reading paper B could ground answers in paper A). The client sends only `{question, selected_text, source_*}`; explicit `paper_id` is sent only via a "Change Paper…" override picker (⇧⌘P) — needed for URL-less contexts like PDFs in Preview. The space dropdown is now only the ingest target for unknown URLs; on resolve the space switches to the owning space (the `resolved` event carries `space`).
- **Cross-space URL lookup:** `find_paper_anywhere(url, prefer_space)` returns `(space, paper_id)`, preferring the requested space on multi-match. `ask()` retargets to the owning space — fixes duplicate-ingestion-into-wrong-space.
- **Preview endpoint `POST /api/resolve`:** the composer must show ●/○ BEFORE the user asks, but the decision needs paper.md which lives server-side — so the client asks the server to pre-run the identical `find_section` + `_should_continue` logic (no side effects, no LLM). It's recomputed on send, so the label can never lie.
- **Fresh is an explicit escape hatch:** `ask(..., fresh=False)` param, `POST /ask` body field, CLI `--fresh`, Raycast ⌘N.
- **New SSE events before tokens:** `{"status": "resolved", "space": ..., "paper": {paper_id, title}}` and `{"status": "thread", "section": ..., "continued": bool}` — the client can retarget the space and show thread state before the first token.
- **Chat-style Raycast UI:** one window, two phases (Composer ↔ ThreadView), no navigation-stack growth. Hotkey always lands on the Composer (WhatsApp-style). ⏎ "Ask Follow-up" returns to the composer from the transcript; follow-up action hidden while streaming.
- **Operational notes:** the daemon must be started from the project root — it discovers `.env` (now `OPENROUTER_API_KEY`; was `GEMINI_API_KEY` before 9.7) via cwd (python-dotenv); started elsewhere it returns "OPENROUTER_API_KEY is not set. Add it to your .env file.". A stale daemon from 9 days prior was silently serving old code on port 8765 (masked by a failed redirect) — check `lsof -nP -iTCP:8765` when behavior seems stale.

### What was built (9.7 — LLM provider abstraction via OpenRouter)

```
paper_agent/llm/
  base.py               # REWRITE: LLMClient — concrete base class holding the ENTIRE OpenAI-compatible
                        #   transport (AsyncOpenAI client created once in __init__; streaming generate();
                        #   generate_structured() with json_object mode + plain-completion fallback +
                        #   markdown-fence stripping). LLMNotConfiguredError lives here.
  openai_client.py      # Thin wrapper: OpenAIClient(LLMClient) — pins the provider name only. Any model
                        #   slug the endpoint serves (e.g. someorg/luna) works without code changes.
  gemini.py             # REWRITE: GeminiClient(LLMClient) thin wrapper — Gemini served via OpenRouter,
                        #   no google-genai SDK. normalize_gemini_model() prefixes bare names with
                        #   "google/" (gemini-2.5-flash → google/gemini-2.5-flash).
  __init__.py           # get_client() factory: provider from config.yaml `provider` key or inferred from
                        #   the model slug (google org / gemini* → gemini; else openai); initializes the
                        #   client with model + OPENROUTER_API_KEY + base_url.
  (vision path removed) # Image support never added to the base client; no audio yet either
paper_agent/
  config.py             # DEFAULT_MODEL = google/gemini-3.7-flash; single OPENROUTER_API_KEY env var;
                        #   OPENROUTER_BASE_URL env / config base_url override; get_llm_settings() →
                        #   {provider, model, api_key, base_url, key_env, key_error}
  agent/                # ask.py, summarize.py, synthesize.py, knowledge.py — all LLM calls via
                        #   get_client(); provider-aware PaperAgentError when the key is missing
  session/writer.py     # Slug generation via get_client() (heuristic fallback unchanged)
  ingestion/
    pipeline.py         # Gemini Vision OCR fallback branch REMOVED — scanned PDFs with no extractable
                        #   text fail with "No content could be extracted" (pymupdf4llm's built-in
                        #   Tesseract OCR still covers partially-scanned pages)
    (fallback.py        # DELETED — the Gemini Vision scanned-PDF OCR fallback)
  api/server.py         # 503 detail is now the provider-aware key error ("OPENROUTER_API_KEY is not
                        #   set. Add it to your .env file.")
  cli.py                # status shows provider / model / base_url / key env name
.env                    # GEMINI_API_KEY → OPENROUTER_API_KEY (an OpenRouter key — provider API keys
                        #   don't authenticate against OpenRouter; BYOK is optional and server-side)
pyproject.toml          # google-genai removed, openai added
```

### Key decisions (9.7)

- **One transport, thin providers:** every model is reachable through OpenRouter's OpenAI-compatible chat-completions API, so `base.py` owns streaming + structured JSON exactly once; provider classes only pin identity (name, model normalization). Adding a provider = a 5-line subclass + a registry entry in `PROVIDERS`.
- **Model selection is plug-and-play:** change `model:` in config.yaml (`someorg/luna`, `google/gemini-3.7-flash`, …) — the provider is inferred from the slug; an explicit `provider:` key overrides. No code changes to swap models.
- **Single OPENROUTER_API_KEY:** provider API keys (Google AI Studio, OpenAI, …) don't work against OpenRouter — one OpenRouter key authenticates everything. A per-provider `openrouter_<org>_key` env pattern was built first, then collapsed to the single key once this was understood.
- **Vision removed deliberately:** image input was only ever used by the scanned-PDF OCR fallback; that whole path is deleted (user: "we will never need image processing"). Audio, if ever needed, would be a separate optional capability on `LLMClient` (OpenRouter accepts audio content parts) — not baked into the text path.
- **Structured output stays schema-driven:** `generate_structured()` injects the JSON schema into the prompt and requests `json_object` mode, falling back to a plain completion and fence-stripping — portable across OpenRouter's heterogeneous models.

### Ideas status

| # | Idea | Status | Notes |
|---|------|--------|-------|
| 9.1 | **Prompt tuning** | ❌ Not started | Design notes below |
| 9.2 | **New project spaces from Raycast** | ⬇️ Dropped | With paper-centric resolution ("space follows paper"), the flow only breaks for a brand-new topic space — rare and deliberate; one terminal `paper-agent init` remains acceptable. (`POST /api/spaces` was never built.) |
| 9.3 | **View notes in Raycast** | ✅ Covered | `session-history` command + the new ⌘H thread view; Obsidian for long-form |
| 9.4 | **Loop mode — collect notes in a single file** | ✅ Done | Implemented as automatic per-paper grouping (keyed by resolved paper / source_url), NOT a toggle — simpler than the plan's "reading-mode flag" idea |
| 9.5 | **Conversation continuity (follow-up questions)** | ✅ Done | Implemented statefully server-side via the vault — the plan's stateless-vs-stateful open question resolved: "the vault IS the conversation state"; client sends no conversation_history |
| 9.6 | **Space control plane (Raycast)** | ❌ Not started | `spaces.tsx` doesn't exist; `POST /api/spaces` not built. Design notes below |
| 9.7 | **LLM provider abstraction (OpenRouter)** | ✅ Done (unplanned) | base transport + thin provider wrappers; single `OPENROUTER_API_KEY`; default model `google/gemini-3.7-flash`; google-genai SDK + Gemini Vision OCR fallback removed. Emerged from wanting luna as a model option |

### Design notes (remaining: 9.6, 9.1)

**Space control plane (9.6):**

A new Raycast command: **"Paper Agent Spaces"** — a `List` view with two levels.

**Level 1 — Space list:**
- Shows all spaces with paper count + session count
- `⏎` → push to space detail (level 2)
- `⌘N` → create new space (prompt for name, calls `POST /api/spaces`)
- API endpoint needed: `POST /api/spaces` (~5 lines: accept `{name}`, call `vault.create_space()`)

```
┌──────────────────────────────────────────────┐
│  Paper Agent Spaces                          │
│  ──────────────────────────────────────────  │
│  🔬 research          4 papers · 3 sessions  │
│  📚 health-policy     0 papers · 0 sessions  │
│                                              │
│  Actions: ⏎ Open  · ⌘N New Space            │
└──────────────────────────────────────────────┘
```

**Level 2 — Space detail:**
- **Papers section** — lists all papers with title, type (pdf/html), page count
  - `⏎` on a paper → open `paper.md` content in a Detail view (read inline)
  - `⌘A` on a paper → jump to ask form with space + paper pre-filled
- **Sessions section** — lists recent sessions with slug, date, Q&A count
  - `⏎` on a session → push to session detail (reuses existing `session-history.tsx` navigation)
- **Space-level actions (ActionPanel):**
  - `⌘I` → Ingest paper (prompt: paste URL → `POST /api/spaces/{name}/papers {url}`)
  - `⌘S` → Browse all sessions (push to existing session-history view)
  - `⌘D` → Purge space contents (confirmation dialog + secret prompt → `DELETE /api/spaces/{name}/contents`)
  - `⌘⌫` → Delete space (confirmation dialog + secret prompt → `DELETE /api/spaces/{name}`)

```
┌──────────────────────────────────────────────┐
│  research                                    │
│  ──────────────────────────────────────────  │
│  📄 Attention Is All You Need        15 pg   │
│  📄 Eagle: Efficient Router            8 pg   │
│  📄 OpenFraming                        9 pg   │
│  📄 Prompt Engineering               (html)   │
│                                              │
│  📝 Sessions                                 │
│  transformer-ml — 2026-07-08 (Q2)            │
│  attention-innovation — 2026-07-08 (Q1)      │
│                                              │
│  Actions:                                    │
│    ⏎ Open paper / session                    │
│    ⌘A Ask about this paper                   │
│    ⌘I Ingest paper (paste URL)               │
│    ⌘S Browse sessions                        │
│    ⌘D Purge space (dangerous)                │
│    ⌘⌫ Delete space (dangerous)               │
└──────────────────────────────────────────────┘
```

**Backend changes needed:**
- `POST /api/spaces` — create a new space. Body: `{name: string}`. Calls `vault.create_space()`. Returns `{name, path}`. ~5 lines.
- All other endpoints already exist (`GET /api/spaces`, `GET /api/spaces/{name}/papers`, `GET /api/spaces/{name}/sessions`, `POST /api/spaces/{name}/papers`, `DELETE /api/spaces/{name}/contents`, `DELETE /api/spaces/{name}`)

**What Obsidian still does better:**
- Reading full `paper.md` with syntax highlighting + math rendering
- Graph view showing links between papers and sessions
- Full-text search across the vault
- Long-form reading of Q&A history

**File:** `raycast-extensions/paper-agent/src/spaces.tsx` — new command added to `package.json` commands array.

**Prompt tuning (9.1):**
- Current prompts live in `paper_agent/llm/prompts.py` — hardcoded
- Could move to `config.yaml` or per-space `prompts.yaml` for customization
- Experiment with: answer length, citation style, "explain like I'm a grad student" vs "be technical", whether to quote the selected text in the answer
- Maybe add a `--style` flag: `concise`, `detailed`, `eli5`, `technical`

**Planned verify (when 9.6 / 9.1 ship):**

```
# Space control plane (9.6)
# Open Raycast → "Paper Agent Spaces"
# → See research (4 papers, 3 sessions) and health-policy (0 papers)
# ⏎ on research → see papers list + sessions list
# ⏎ on "Attention Is All You Need" → read paper.md inline in Detail view
# ⌘A on a paper → ask form opens with space + paper pre-filled
# ⌘I → paste arxiv URL → paper ingested → appears in list
# ⌘N at space list → type "nlp-fundamentals" → space created → appears in list

# Prompt tuning
paper-agent ask "explain attention" --space research --style concise
# → 2-3 sentence answer instead of full paragraph
```

### Superseded design notes (9.4, 9.5 — see "What was built" for what shipped)

**Loop mode (9.4) — superseded:** The plan proposed a per-session toggle between "session" (dated files) and "reading" mode, with explicit open/close and auto-close on paper switch. What shipped is simpler: reading sessions are automatic — any ask that resolves to a paper appends to `sessions/reading-{paper-slug}.md` (frontmatter: `paper`, `reading_session: true`, `started_at`, `qa_count` updated per append, `source_url`). Non-paper asks keep the dated-file + AI-slug path. No toggle, no explicit close; grouping is keyed by resolved paper / source_url.

**Conversation continuity (9.5) — superseded:** The plan weighed stateless (client sends `conversation_history` in the POST body) vs stateful (daemon remembers) and leaned stateless. What shipped is stateful server-side: `ask()` loads the last 5 turns from the reading file, decides follow-up vs fresh via section matching (`_should_continue`), and injects prior Q&A into the prompt as "**Earlier in this conversation:**" turns. The client never sends history — the vault IS the conversation state. An explicit `fresh` flag (API body field / CLI `--fresh` / Raycast ⌘N) is the escape hatch.

### Verified (9.4 + 9.5)

```
# Reading session: same paper → one file, section recorded
paper-agent ask "what do position-wise feed-forward networks do?" --space research --paper attention-is-all-you-need --selected "..."
# → Saved to ~/.paper-vault/spaces/research/sessions/reading-attention-is-all-you-need.md
# → entry has **Section:** Attention Is All You Need > 3 Model Architecture > 3.3 Position-wise Feed-Forward Networks
# → frontmatter qa_count increments on appends

# Thread events (API, daemon with new code)
curl -N -X POST localhost:8765/api/spaces/research/ask ...
# → data: {"status": "resolved", "space": "research", "paper": {"paper_id": "attention-is-all-you-need", "title": "Attention Is All You Need"}}
# → data: {"status": "thread", "section": "3.5 Positional Encoding", "continued": false}   (different section from last)
# → same-section follow-up → {"status": "thread", "section": "3.3 ...", "continued": true}
# → "fresh": true in body → continued: false even when section matches

# Cross-space retarget: ask against a scratch space holding the URL
# → resolved event reports "space": "research", session saved to research, scratch space stayed EMPTY (no duplicate ingest)

# Resolve preview states
POST /api/resolve {url, same-section selection}   → continuing | 3.3 ... | qa_count
POST /api/resolve {url, other-section selection}  → fresh | 3.5 Positional Encoding
POST /api/resolve {unknown url}                   → new_paper
POST /api/resolve {no url, selection}             → no_paper
POST /api/resolve {}                              → found active paper, continuing §3.3, 10 prior Q&A

# No-URL/no-selection ask ("can you restate that more simply?")
# → resolved last active paper, thread continued §3.3, answer re-explained the previous answer, stored with inherited §3.3
# Chain test: follow-up WITH a §3.3 selection → continued: true (chain preserved)

# Raycast
npx tsc --noEmit    ✓ 0 errors
npm run build       ✓ 4 entry points compiled
```

### Notes for next phase (remaining Phase 9)

- Phase 9.5 (Summary + Synthesis Polish) is DONE (see its section above).
- Remaining Phase 9 items: 9.1 prompt tuning, 9.6 space control plane (design notes above)
- Operational: daemon must be started from the project root (`.env` discovery via cwd); check `lsof -nP -iTCP:8765` for stale daemons when behavior seems stale
- pymupdf4llm heading-mangling caveat affects section matching (see Key decisions)
- The research vault was rebuilt fresh during 9.5 verification (2 papers, seeded Q&A, real summaries/synthesis)

---

## Phase 9.5: Summary + Synthesis Polish ✅ Done

**Goal:** Fix reliability and usability issues discovered while verifying Phase 7's summarize and synthesize endpoints. These are small fixes that make the knowledge compounding flow trustworthy before building on top of it.

### Issues found during Phase 7 verification

| # | Issue | Severity | Resolution |
|---|-------|----------|------------|
| 1 | **Synthesize is non-deterministic** — same inputs produce different outputs across calls. Sometimes returns 0 connections, sometimes 2. | High | Fixed inherently (see 9.5.2 design below) — not with temperature/retry band-aids |
| 2 | **Summaries silently overwritten** — no version history. | Low | Not addressed (regenerable artifact; optional 9.5.5 skipped) |
| 3 | **Inconsistent JSON storage** — summary JSON in `metadata.yaml`, synthesis JSON in `summaries/synthesis.json`. | Low | Standardized on sidecar `.json` files (9.5.4) |
| 4 | **No staleness tracking** — no flag indicates "this paper has new Q&A since last summary." | Medium | `summarized_qa_count` in `summary.json` + staleness surfaced everywhere (9.5.3) |

### What was built

```
paper_agent/
  llm/
    base.py               # +reasoning_effort param — passed to every completions call as
                          #   OpenRouter extra_body {"reasoning": {"enabled": true, "effort": ...}}
                          #   +aclose() — explicit client close
                          #   +install_asyncgen_teardown_filter() — loop exception handler that
                          #   downgrades the httpcore2 asyncgen finalization noise (root-caused,
                          #   see Key decisions); installed automatically by LLMClient.__init__
    __init__.py           # +get_structured_client() — factory for structured-call clients;
                          #   shared _build_client() helper
  config.py               # +get_structured_llm_settings() — structured_model /
                          #   structured_provider / structured_reasoning_effort config.yaml keys
                          #   (all fall back to the main model / reasoning_effort);
                          #   get_llm_settings() also returns reasoning_effort;
                          #   DEFAULT_MODEL = openai/gpt-5.6-luna; _infer_provider() extracted
  agent/
    synthesize.py         # REWRITE: one-vs-rest verdict design (see below)
    summarize.py          # +summary.json sidecar {summary, summarized_qa_count, summarized_at,
                          #   model}; metadata.yaml goes back to purely descriptive (legacy
                          #   `summary` key popped on re-summarize); uses structured client
    ask.py                # closes the LLM client after streaming (finally: aclose())
    knowledge.py          # reads summaries via vault.get_paper_summary() (sidecar + legacy
                          #   fallback); uses structured client
  session/writer.py       # _generate_slug closes its client too
  llm/prompts.py          # SYNTHESIS_SCHEMA/build_synthesize_prompt REPLACED by:
                          #   SYNTHESIS_VERDICTS_SCHEMA + build_synthesize_pairwise_prompt()
                          #   (forced per-pair verdicts) + OVERALL_SYNTHESIS_SCHEMA +
                          #   build_overall_synthesis_prompt()
  vault.py                # +get_paper_summary(space, paper_id) — reads summary.json sidecar,
                          #   falls back to legacy metadata.yaml `summary` key (freshness = None);
                          #   +is_summary_stale(space, paper_id) → bool | None;
                          #   regenerate_index shows "⚠ stale" on stale summary links
  api/server.py           # papers list + has_summary / summary_stale / qa_count /
                          #   summarized_qa_count; summarize/synthesize/knowledge/open-questions
                          #   key-check now uses structured settings
  cli.py                  # status shows "(reasoning: …)" on the model line when configured
~/.paper-vault/.paper-agent/config.yaml   # model: openai/gpt-5.6-luna, reasoning_effort: low —
                          #   ONE model for everything (structured_* keys supported but unused)
```

### Key decisions

- **9.5.1 — no temperature=0; one model for everything.** Instead of pinning temperature, structured calls (summarize, synthesize, knowledge, open-questions) route to a dedicated **structured client** — configured via `structured_model` / `structured_reasoning_effort` in config.yaml, falling back to the main `model` / `reasoning_effort`. Determinism comes from the forced-verdict schemas + a reasoning model, not sampling knobs. After verification the split was collapsed: **everything (streaming ask included) now runs `openai/gpt-5.6-luna` at `reasoning: low`** — `DEFAULT_MODEL` is luna, and the vault config is just `model` + `reasoning_effort`. The structured_* keys remain supported for a future split if streaming answers ever need a different model.
- **9.5.2 — one-vs-rest verdicts, not retry-union.** The old prompt was open-ended ("find connections across N papers; empty array is valid") — a lazy bail-out the model took randomly. Retry+union was rejected as a band-aid: with deterministic sampling it re-asks the same question, and it can't distinguish "no connections" from "model bailed". The inherent fix: **each paper runs against all remaining papers in ONE call** (paper i vs papers i+1..N — every pair judged exactly once, N-1 calls total), and the schema **forces a verdict for every other paper** (`related: bool` + relationship + insight; `unrelated` is an explicit relationship value). Emptiness is impossible by construction — "no connections" is now a verified negative, surfaced in `cross-paper-insights.md` as a "Judged Unrelated" section. A single retry remains only as a JSON-malformation safety net (`_verdicts_for`). A final call generates `overall_synthesis` from the confirmed connections; zero connections short-circuits to a canned honest string.
- **9.5.3 — freshness lives with the summary.** `summary.json` records `summarized_qa_count`, `summarized_at`, and the model that wrote it. Staleness = current `get_qa_by_paper()` count ≠ `summarized_qa_count`, surfaced as: `summary_stale` in `GET /api/spaces/{name}/papers`, "⚠ stale" in `index.md`, and `is_summary_stale()` for any future consumer. Legacy summaries (embedded in metadata.yaml, no count) report staleness as unknown (None), not stale.
- **9.5.4 — sidecar `.json` everywhere.** `papers/{slug}/summary.json` and `summaries/synthesis.json` are THE structured-storage locations; `metadata.yaml` is purely descriptive. Readers (`synthesize`, `knowledge`, `vault.get_paper_summary`) fall back to the legacy metadata.yaml `summary` key so pre-9.5.4 vaults keep working; re-summarizing migrates a paper automatically (legacy key popped).
- **synthesis.json shape:** `{connections: [{paper_a, paper_b, relationship, insight}], unrelated: [same], overall_synthesis}` — the API response contract (`status`, `connections` count, `markdown`) is unchanged, so the Raycast extension needed no changes. 0-connection runs now return `status: ok` with `connections: 0` (a verified negative) instead of "skipped".
- **Optional 9.5.5 (summary-previous.md) skipped** — summaries are regenerable artifacts; revisit only if tracking understanding evolution becomes valuable.
- **Asyncgen teardown noise — root-caused and filtered, not suppressed blindly.** Streaming asks printed `RuntimeError: generator didn't stop after athrow()` tracebacks ("an error occurred during closing of asynchronous generator"). Minimal repro + generator inventory showed: openai 3.8's SSE loop `break`s on the `[DONE]` event without exhausting httpcore2's response-body generator chain — 10 orphaned generators stay suspended (openai `_iter_events`/`aiter_bytes` → httpx2 → httpcore2 `PoolByteStream.__aiter__`/`HTTP11ConnectionByteStream.__aiter__`/`_receive_response_body`/`safe_async_iterate`). When GC finalizes them, asyncio athrows GeneratorExit, and httpcore2's `except BaseException: await self.aclose(); raise exc` pattern inside nested async-context managers fails the asyncgen close protocol. Crucially there is **no leak**: openai's `finally: await response.aclose()` already released the connection (httpcore2's later aclose is a no-op, guarded by `_closed`) — the daemon showed zero per-request accumulation. `LLMClient.__init__` now installs a loop exception handler that matches exactly this failure (RuntimeError "generator didn't stop after athrow()") and logs it at debug, delegating everything else to the previous/default handler. Upstream-worthy (openai's break-on-[DONE] × httpcore2's close-intolerant generators); revisit when either library fixes it.

### Verified

```
paper-agent status
# → provider: openai
# → model: openai/gpt-5.6-luna (reasoning: low)     ← one model for everything

# Fresh vault: init research → ingest attention (1706.03762) + eagle (2409.15518)
# → 6 seeded Q&A per paper in reading-*.md session files

paper-agent summarize --space research --paper attention-is-all-you-need
# → summary.md + summary.json {summarized_qa_count: 6, model: openai/gpt-5.6-luna, summarized_at}
# → metadata.yaml: NO summary key (purely descriptive again)

paper-agent synthesize --space research   (run twice, + once via API)
# → 1 connection every run: Attention ↔ Eagle (builds_on / shares_method — same pair,
#   same related verdict; only the label wording varies)
# → no empty bail-outs; unrelated pairs would appear under "Judged Unrelated"

# Streaming ask on luna (CLI + daemon SSE)
paper-agent ask "what budget does it target?" --space research
# → streamed markdown answer grounded in the active paper, saved to the reading session,
#   exit 0, stderr clean (see the asyncgen teardown filter below)
curl -N -X POST localhost:8765/api/spaces/research/ask …
# → SSE tokens + session_path JSON, daemon log clean — no leaked generators per request

# Selection-only ask (slug path) → minimax-bayes-rule-20260904.md with AI-generated slug

# Staleness loop
# append a 7th Q&A to the attention reading file →
#   is_summary_stale → True · index.md shows "[summary](…) ⚠ stale"
#   GET /api/spaces/research/papers → attention: stale=True, qa=7, summarized=6
# POST /api/spaces/research/summarize {paper_id} (via API) →
#   papers list → attention: stale=False, qa=7, summarized=7   ← fresh again

# knowledge + open-questions still work off the new summary.json read path
POST /knowledge       → ok, 5 themes, 9 key facts
POST /open-questions  → ok, 9 questions

# Legacy fallback (scratch vault with metadata.yaml-embedded summary)
get_paper_summary → reads legacy summary, summarized_qa_count None
is_summary_stale  → None (unknown, not false-stale)

python3 -m compileall paper_agent   ✓
```

---

## Phase 10: Multimodal Asks

**Goal:** Handle images, diagrams, equations, and figures — not just text. Papers are visual. A chart, an architecture diagram, a math equation screenshot — all should be askable.

### The problem

Current flow only captures text selection. But papers contain:
- Architecture diagrams (transformer encoder/decoder figure)
- Charts and plots (loss curves, ablation tables)
- Math equations (LaTeX rendered as images in browser)
- Tables (sometimes not selectable as text)

When you select text in a PDF, you get text. When you screenshot a figure, you get an image. The agent should handle both.

### Approaches to explore

| Approach | How it works | Trade-offs |
|----------|-------------|------------|
| **A. Screenshot + Gemini Vision** | User screenshots a region → Raycast captures clipboard image → sends to Gemini Vision API alongside question | Most flexible. Works for any visual. Requires screenshot workflow (Cmd+Shift+4 → clipboard). Gemini supports image input. |
| **B. Figure extraction from ingested PDF** | During PDF ingestion (Phase 6), extract figures/images from PDF → store alongside `paper.md` → when asking about a paper, include relevant figures | Automatic, no user effort. But figure extraction from PDFs is unreliable. Which figure to include? |
| **C. Clipboard image detection** | Raycast detects if clipboard contains an image (not text) → sends image to Gemini Vision | Seamless. If you copy a figure, it just works. But getting images through Raycast/AppleScript is trickier than text. |
| **D. Page-level context** | Send the current page as an image to Gemini → "what does the chart on this page show?" | Requires capturing the visible viewport as an image. Browser screenshots via AppleScript. Heavy on tokens. |

### Recommended starting point

**Approach A (screenshot + vision)** is the most pragmatic:
1. User selects text OR takes a screenshot (`Cmd+Shift+4` → clipboard)
2. Raycast `capture-and-ask` detects: is clipboard text or image?
3. If image → send to `POST /api/spaces/{name}/ask` as multipart with image + question
4. Daemon forwards image + prompt to Gemini Vision (`generate_content` with `types.Part` containing image bytes)
5. Answer streams back as normal

### Steps

| Step | Action | Incremental output |
|------|--------|--------------------|
| 10.1 | Detect clipboard image in Raycast capture flow | `captureContext()` returns `{ image?: Buffer, selectedText: string }` |
| 10.2 | `POST /api/spaces/{name}/ask` — accept multipart form with optional `image` field alongside JSON fields | Daemon receives image bytes |
| 10.3 | Update `gemini.py` — `generate()` accepts optional image bytes → builds `types.Part` with inline_data → passes to `generate_content_stream` | Gemini Vision processes image + text prompt |
| 10.4 | Update `prompts.py` — when image present, prompt references "the attached image/screenshot" | Vision-grounded answers |
| 10.5 | Raycast: if clipboard has image, show "Screenshot captured" in form instead of selected text | User knows image will be sent |
| 10.6 | Session persistence: save image reference in session file (stored in vault, not inline) | `sessions/` can reference `assets/` images |

### Verify

```
# Screenshot a transformer architecture diagram in a PDF
# → Cmd+Shift+4 → select region → clipboard has image
# → Cmd+Shift+P → "Screenshot captured" shown in form
# → Type "explain what each component does"
# → Answer references the diagram: "The encoder on the left has N=6 layers..."

# Screenshot a loss curve
# → "Why does validation loss spike here?"
# → "The spike at epoch 15 suggests..."
```

### Open questions

- Gemini Vision rate limits / cost with image input?
- Best image format to send? (PNG from clipboard vs JPEG for size?)
- Should images be saved in the vault? (`spaces/{name}/assets/` directory?)
- Can we detect if the screenshot is from a paper vs random image?

---

## Phase 11: MCP Adapter

**Goal:** Claude Desktop, Claude Code, and other MCP clients can use paper-agent tools.

### Steps

| Step | Action | Incremental output |
|------|--------|--------------------|
| 11.1 | `paper_agent/mcp/server.py` — MCP server with tools: `list_spaces`, `ask`, `search`, `summarize`, `get_papers`, `get_sessions` | MCP server on stdio |
| 11.2 | `paper_agent/mcp/tools.py` — tool definitions + handlers, each calls existing core functions | Tools appear in Claude |
| 11.3 | `paper-agent mcp` — CLI command runs MCP server on stdio | Ready for Claude Desktop config |
| 11.4 | Claude Desktop config snippet | One JSON entry → tools available |

### Verify
```json
// ~/Library/Application Support/Claude/claude_desktop_config.json
{
  "mcpServers": {
    "paper-agent": {
      "command": "paper-agent",
      "args": ["mcp"]
    }
  }
}
```
```
// In Claude Desktop:
"Search my ml-research papers for anything about transformer architecture"
// → Uses search tool → returns results
```

---

## Phase 12: WhatsApp Bridge (Optional)

**Goal:** Send WhatsApp messages → paper-agent responds with answers from your vault. Requires a reachable endpoint.

### Steps

| Step | Action | Incremental output |
|------|--------|--------------------|
| 12.1 | Evaluate approach: Twilio WhatsApp API vs whatsapp-web.js vs Meta Cloud API | Chosen approach |
| 12.2 | `paper_agent/bridges/whatsapp/` — relay: receives message, parses `{space}: {question}`, calls daemon API, returns answer | `ml-research: explain attention` → answer in WhatsApp |
| 12.3 | Deploy relay on tiny VPS or fly.io, connected to home daemon via Tailscale | Works from anywhere |

### Verify
```
WhatsApp: "ml-research: what is a transformer?"
→ "The Transformer is a neural network architecture..."
```

---

## Summary

| Phase | Status | What you get | Anchored to |
|-------|--------|-------------|-------------|
| 1 | ✅ Done | `paper-agent` CLI exists. Spaces created. | Terminal |
| 2 | ✅ Done | **Ask questions from the terminal.** No PDFs needed. | Terminal |
| 3 | ✅ Done | **Q&A saved to vault.** Visible in Obsidian. | Obsidian |
| 4 | ✅ Done | **Daemon API running.** curl-able, ready for Raycast. | Terminal |
| 5 | ✅ Done | **Cmd+Shift+P → ask → stream.** The daily loop works. | **Raycast** |
| 6 | ✅ Done | **PDF ingestion.** Answers now grounded in full papers. | Obsidian |
| 7 | ✅ Done | **Summaries + compounding knowledge.** Agent writes what it learns. | Obsidian |
| 9 | 🟡 Partial | **Desktop polish.** 9.4 loop mode + 9.5 continuity + 9.7 LLM provider abstraction (OpenRouter) done (reading threads, section-based follow-ups, chat-style Raycast UI, any-model-via-OpenRouter). Remaining: 9.1 prompt tuning, 9.6 space control plane (9.2 dropped, 9.3 covered). | Raycast / Desktop |
| 9.5 | ❌ | **Summary polish.** Temperature=0, synthesize retry, staleness tracking. | Backend |
| 10 | ❌ | **Multimodal asks.** Screenshot a diagram → ask about it. | Raycast / Desktop |
| 11 | ❌ | **MCP.** Claude Desktop integration. | Claude |
| 12 | ❌ | **WhatsApp.** Message from anywhere. | WhatsApp |
| 13 | ❌ | **iPad.** Ask while reading on tablet. | iPad |
| 14 | ❌ | **Voice.** Speak instead of type, across all devices. | All |
| 8 | ⏸️ Deferred | **Search.** Moved to last — Obsidian already covers find; build only if retrieval is ever needed. | Terminal / Raycast |

**Core loop (Phase 5):** select text → Cmd+Shift+P → pick space → type question → streaming answer → auto-saved

**Paper-aware loop (Phase 6):** select text → Cmd+Shift+P → pick space → pick paper → type question → streaming answer grounded in full paper → auto-saved

**Knowledge loop (Phase 7):** summarize paper → synthesize across papers → update knowledge.md → curate open-questions.md → index.md auto-regenerated

**Reading-thread loop (Phase 9):** select text → hotkey → informed composer (●/○ thread status + history + quote) → reply → streamed answer → appended to reading-{paper}.md

Everything before Phase 5 builds toward it. Phases 6–10 make the desktop experience smarter and more complete. Everything after (Phase 11+) extends to other platforms.

---

## Phase 13: iPad Interaction

**Goal:** Read papers on iPad → ask questions without leaving the reading experience. No native app to build. Uses iOS Shortcuts as the trigger layer, with a minimal PWA for richer back-and-forth.

### Three touchpoints, ordered by effort

| # | How | Trigger | Best for |
|---|-----|---------|----------|
| A | iOS Shortcut | Share sheet / keyboard / Siri / widget | Quick asks while reading |
| B | Minimal PWA | Safari bookmark or Home Screen icon | Back-and-forth conversation, browsing history |
| C | Siri voice | "Hey Siri, ask paper agent..." | Hands-free, eyes on paper |

### A: iOS Shortcut (Primary)

```
Reading PDF in Safari/Books/PDF Expert
  → select text
  → tap "Share..."
  → tap "Ask Paper Agent" shortcut
  → menu: "ml-research" / "health" / ...
  → text field: "your question"
  → calls POST /api/spaces/{name}/ask via HTTP
  → shows streaming response in dialog
  → auto-saved to vault
```

**With keyboard (iPad + Magic Keyboard):** Set the shortcut to trigger on `Cmd+Shift+A`. The flow becomes: select text → `Cmd+Shift+A` → type question → Enter → see response.

**With Siri:** "Hey Siri, ask paper agent" → Siri prompts "Which space?" → "ml-research" → "What's your question?" → "explain this attention mechanism" → Siri reads the response aloud.

**What gets built:**
- One `.shortcut` file (JSON, can be committed to repo)
- Shortcut actions: Read share sheet input → Get spaces from API → Choose from list → Ask for text input → POST to daemon → Show result
- No code. Built entirely in Shortcuts app GUI, exported as file.

### B: Minimal PWA (Secondary)

A single-page web app served by the daemon itself. Open in Safari → "Add to Home Screen" → looks and feels like an app.

```
┌──────────────────────────────┐
│  Paper Agent                 │
│  ──────────────────────────  │
│  Space: [ml-research    ▼]   │
│                              │
│  ┌──────────────────────────┐│
│  │ Q: explain self-attention││
│  │ A: Self-attention is...  ││
│  │                          ││
│  │ Q: what about Figure 3? ││
│  │ A: Building on the...   ││  ← scrollable thread
│  └──────────────────────────┘│
│                              │
│  [________________________]  │
│  [Send]                      │
└──────────────────────────────┘
```

**What gets built:**
- `paper_agent/web/chat.html` — single HTML file with vanilla JS, served via FastAPI static route
- Fetches spaces from API, renders dropdown
- SSE streaming for responses
- Scrollable conversation thread
- Add to Home Screen meta tags (PWA manifest, icon)
- ~150 lines of HTML/CSS/JS

### C: Siri Integration

The iOS Shortcut from (A) is also a Siri intent. Add a custom Siri trigger phrase: "Ask paper agent." Then:

> "Hey Siri, ask paper agent."
> Siri: "Which space?"
> "ml-research."
> Siri: "What's your question?"
> "Why does multi-head attention help?"

Siri reads the first ~300 characters of the response. For long answers, it says "The full response is in your vault."

### Network: Making the daemon reachable from iPad

The daemon runs on your Mac. iPad needs to reach it.

| Option | Setup | Effort |
|--------|-------|--------|
| **Tailscale** (recommended) | Install on Mac + iPad. iPad uses `http://mac-name:8765` | 2 min, free |
| Same WiFi | iPad uses `http://mac-ip:8765` | 0 min, fragile |
| iCloud Relay | Not applicable | — |
| Expose via VPS | Overkill for this | — |

Shortcut stores the daemon URL as a variable. Easy to switch between "home WiFi" and "Tailscale" URLs.

### Verify

```
1. paper-agent serve running on Mac
2. Tailscale on both devices, or same WiFi
3. iPad: open Safari → select text in arxiv paper
4. Tap Share → "Ask Paper Agent" shortcut
5. Select "ml-research" from menu
6. Type "explain this section"
7. Response streams in dialog
8. Open Obsidian (or PWA) → Q&A saved
```

### Summary of all entry points

| Device | Method | Trigger |
|--------|--------|---------|
| Mac | Raycast extension | `Cmd+Shift+P` |
| Mac | Terminal CLI | `paper-agent ask ...` |
| iPad | iOS Shortcut | Share sheet / `Cmd+Shift+A` |
| iPad | PWA (Safari) | Home Screen icon tap |
| iPad/iPhone | Siri | "Hey Siri, ask paper agent" |
| Anywhere | WhatsApp | Message |
| Desktop | Claude Desktop | MCP tools |

---

## Phase 14: Voice Input (Optional)

**Goal:** Speak questions instead of typing. One `transcribe` endpoint on the daemon, then voice capture added to each client in whatever way is most native to that platform. After transcription, it's the same `ask()` pipeline — voice is decoration, not a separate product.

**Architecture:**

```
Any client                    daemon
┌──────────┐    audio/webm    ┌──────────────┐
│ capture  │ ───────────────▶ │ /transcribe  │
│ mic      │                  │  (Groq       │
│ (native) │ ◀─────────────── │   Whisper)   │
└──────────┘    {text: "..."} └──────┬───────┘
                                     │ text
                                     ▼
                              ┌──────────────┐
                              │ /ask         │
                              │  (same pipe) │
                              └──────┬───────┘
                                     │ SSE stream
                                     ▼
                              ┌──────────────┐
                              │ vault        │
                              └──────────────┘
```

### Daemon: Transcription Endpoint

| Step | Action |
|------|--------|
| 12.1 | `POST /api/transcribe` — accepts audio blob (multipart/form-data, any format: webm, m4a, wav, mp3). Returns `{text: "transcribed text"}` |
| 12.2 | Backend: Groq Whisper API (`whisper-large-v3`). ~$0.004/minute. Latency: ~500ms for a 10-second clip. |
| 12.3 | Fallback option: local Whisper via `faster-whisper` (free, ~2GB model download, 2-3x slower than Groq). Config toggle in `config.yaml`. |

### Per-Platform Voice Capture

#### A. Raycast (Mac) — "Hold to Talk"

A separate Raycast command: "Ask Paper Agent (Voice)."

```
Hold Cmd+Shift+V → mic icon shows "● Recording..."
  │
  ├── Speak question
  │     (max 20s, auto-stops with notification)
  │
  └── Release Cmd+Shift+V
        │
        ├── Audio blob sent to daemon /transcribe
        ├── Transcription appears in Raycast for review (editable before submit)
        ├── Space auto-detected (last used) or shown as dropdown
        ├── User confirms (Enter) or edits and confirms
        └── Response streams inline as normal
```

**Why separate command (not inline mic button):** Stay focused while reading. No dropdowns. Hold, speak, release, review, confirm. The "Hold to Talk" pattern from the original PRD, now native to Raycast.

**Builds on:** Phase 5 Raycast extension. Adds one extra command file.

#### B. WhatsApp — Voice Notes

WhatsApp already has voice notes. No UI to build. The bridge handles it:

```
User sends voice note in WhatsApp
  → Bridge receives audio message (native WhatsApp type)
  → Forwards audio to daemon POST /api/transcribe
  → Transcribed text treated as question
  → Auto-detects space from last used or recent context
  → Runs ask() with transcribed text
  → Returns answer as text message
  → Optionally: attaches the transcribed text above the answer
      ("You asked: explain attention heads")
```

**With space prefix in voice note caption:** User types "ml-research" in the caption field before sending the voice note. No caption = use last space.

**Builds on:** Phase 10 WhatsApp bridge. Adds audio message handler.

#### C. iPad (iOS Shortcuts) — Native Dictation

iOS has world-class on-device dictation. No Whisper needed. The shortcut uses the built-in "Dictate Text" action.

```
Select text in Safari/PDF reader
  → Share → "Ask Paper Agent (Voice)" shortcut
  → Pick space (tap or Siri reads options, you say "ml-research")
  → iOS Dictate Text action activates → speak your question
  → Shortcut sends {question: "transcribed text", selected_text: ...} to POST /ask
  → Response shown in dialog or opened in PWA
```

The same shortcut works for typing AND voice — just choose "Dictate Text" instead of "Ask for Text Input" as the input action.

**Alternative: "Hey Siri, ask paper agent"** → Siri prompts "What's your question?" → you speak → Siri transcribes → shortcut calls daemon → Siri reads answer aloud. The most frictionless flow. No screen interaction at all.

**Builds on:** Phase 11 iPad Shortcut. Adds Dictate Text action variant.

#### D. iPad (PWA) — In-Browser Recording

The PWA gets a mic button next to the text input.

```
Tap mic icon → browser shows "Allow microphone" prompt
  → Hold to record (touch and hold the mic button)
  → Release to send
  → Audio blob → POST /transcribe → text → POST /ask
  → Response streams into the chat thread
```

Uses the browser's `MediaRecorder` API. Works in Safari since iOS 14.5.

**Builds on:** Phase 11 PWA. Adds ~30 lines of JS for MediaRecorder + mic button.

#### E. CLI — Voice Flag

```
$ paper-agent ask --voice --space ml-research
```

Same flow: records from default mic → writes to temp file → POSTs to daemon → transcribes → asks. Shows the transcription so you can verify before it sends: "You asked: why does multi-head attention help with long sequences?" then streams answer.

**Or skip the daemon and use Groq directly from CLI** for lower latency (CLI → Groq → text → daemon /ask instead of CLI → daemon → Groq → daemon /ask).

### Summary: Voice Entry Points

| Device | Voice Method | How It Works | Whisper Needed? |
|--------|-------------|-------------|-----------------|
| Mac | Raycast "Hold to Talk" | Hold `Cmd+Shift+V` → speak → release → transcribe → ask | Yes (daemon) |
| Mac | CLI `--voice` | `paper-agent ask --voice` → record mic → transcribe → ask | Yes (daemon) |
| iPad/iPhone | iOS Shortcut + Dictate Text | Share sheet → pick space → iOS dictation → ask | No (iOS native) |
| iPad/iPhone | Siri | "Hey Siri, ask paper agent" → speak → Siri transcribes → ask | No (Siri native) |
| iPad | PWA mic button | Tap mic → hold to record → release → transcribe → ask | Yes (daemon) |
| Anywhere | WhatsApp voice note | Record voice note → bridge transcribes → ask | Yes (daemon) |

### Verify

```bash
# Daemon transcribe test
curl -F "audio=@question.webm" localhost:8765/api/transcribe
# → {"text": "what is the attention mechanism"}

# Full voice flow (CLI)
paper-agent ask --voice --space ml-research
# Recording... (speak, Ctrl+C to stop)
# Transcribed: "explain the query key value concept"
# (streaming answer follows)
```

```
# Raycast: hold Cmd+Shift+V → speak → release
# → "why is positional encoding needed?" appears in review field
# → press Enter → answer streams
```

### Whisper Provider Decision

| Provider | Cost | Speed | Setup |
|----------|------|-------|-------|
| **Groq Whisper** (recommended) | $0.004/min (~$0.0004 per 10s question) | ~500ms | API key |
| faster-whisper (local) | Free | 2-5s | Download 2GB model |
| OpenAI Whisper | $0.006/min | ~1s | API key |

Recommendation: start with Groq (fast, cheap enough that 1,000 voice questions cost ~$0.40). Add local fallback in config for offline use.

---

## Phase 8: Search (Deferred — build last, only if needed)

> **Why deferred (2026-08):** Every consumer of search already has an answer. Human-facing find is covered by Obsidian full-text search and the Raycast `session-history` command. `ask()` injects full `paper.md` (~10-15K tokens) into a 1M-token context, so no retrieval infrastructure is needed at current scale. Cross-paper sensemaking is covered by Phase 7's `synthesize` / `knowledge.md`. Nothing breaks if this phase never ships.
>
> **Revisit when:** a space grows to ~30-50 papers and picking the right paper from the dropdown gets annoying; `ask()` quality degrades because relevant papers are missed; or ad-hoc cross-paper questions become frequent. If that happens, prefer retrieval built *inside* `ask()` (agentic grep/read tools, or summaries-in-context) over a standalone search product — and skip GraphRAG/contextual RAG, which are redundant with Phase 7 artifacts at this scale.

**Goal:** Fast text search across papers + sessions + summaries. Optional semantic/embedding search.

### Steps

| Step | Action | Incremental output |
|------|--------|--------------------|
| 8.1 | `paper_agent/search/text_search.py` — walk vault, grep-like text search across all .md files in a space | `search("attention mechanism")` → ranked results with file + line snippets |
| 8.2 | `paper-agent search ml-research "multi-head attention"` — CLI command | Terminal search with context snippets |
| 8.3 | `GET /api/spaces/{name}/search?q=...` — API endpoint | Raycast search command |
| 8.4 | `paper_agent/index/sqlite.py` — build `.paper-agent/index.sqlite` for faster lookups (papers, sessions, qa_pairs) | Indexed search for spaces with many papers |
| 8.5 | Optional: `paper_agent/search/embeddings.py` — Gemini embedding API (free tier) for semantic search | `search("how do models scale?", semantic=true)` |

### Verify
```bash
paper-agent search ml-research "transformer"
# → attention-is-all-you-need/paper.md:42 "The Transformer uses..."
# → sessions/2026-05-03-ml-research.md Q3 "Q: what is a transformer?"
```
