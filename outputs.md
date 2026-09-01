# Project Status — paper-agent

## Where we are

| Phase | Status | What works |
|-------|--------|------------|
| 1 — Scaffold + Vault + Spaces | ✅ Done | `paper-agent init/status/serve`, vault tree, config |
| 2 — Ask (No PDF) | ✅ Done | CLI `paper-agent ask` streams Gemini answers with selected-text context |
| 3 — Session Persistence | ✅ Done | Q&A auto-saved to dated session files, `index.md`, context tracking |
| 4 — Daemon API (HTTP + SSE) | ✅ Done | FastAPI server, 7 endpoints, CORS, SSE streaming |
| 5 — Raycast Hotkey | ✅ Done | Select text → hotkey → space → question → streamed answer → auto-saved |
| 6 — PDF Ingestion | ✅ Done | PDF/HTML ingestion, auto-ingest in ask, paper-aware answers, Raycast paper picker |
| 7 — Summaries + Knowledge | ✅ Done | Paper summaries, `knowledge.md`, `open-questions.md`, cross-paper synthesis, enhanced `index.md` |
| 8 — Search | ⏸️ Deferred to last | Obsidian covers find; no consumer needs a search index yet |
| 9 — Desktop Polish | 🟡 Partial | 9.4 loop mode + 9.5 continuity + 9.7 LLM provider abstraction done (reading threads, section-based follow-ups, chat-style Raycast UI, any-model-via-OpenRouter); remaining: 9.1 prompt tuning, 9.6 space control plane; 9.2 dropped, 9.3 covered |
| 9.5 — Summary Polish | ❌ Not started | Temperature=0, synthesize retry, staleness tracking, JSON storage consistency |
| 10 — Multimodal Asks | ❌ Not started | Screenshot → Gemini Vision, diagram/chart/equation asks |
| 11 — MCP Adapter | ❌ Not started | Claude Desktop / Claude Code integration |
| 12 — WhatsApp Bridge | ❌ Not started | WhatsApp → daemon relay |
| 13 — iPad Interaction | ❌ Not started | iOS Shortcuts + PWA + Siri |
| 14 — Voice Input | ❌ Not started | Groq Whisper transcription, hold-to-talk |

**Core loop (Phases 1–5):** select text → hotkey → pick space → type question → streaming answer → auto-saved to vault → visible in Obsidian.

**Paper-aware loop (Phase 6):** select text → hotkey → pick space → pick paper → type question → streaming answer grounded in full paper → auto-saved. Auto-ingests from URL if paper not yet in vault.

**Desktop completion (Phases 6–10):** PDF ingestion, summaries, search, desktop polish, multimodal — make the Mac experience complete before building external integrations.

**Knowledge loop (Phase 7):** summarize paper → synthesize across papers → update knowledge.md → curate open-questions.md → index.md auto-regenerated with links to all artifacts.

**Reading-thread loop (Phase 9):** select text → hotkey → informed composer (●/○ thread status + history + quote) → reply → streamed answer → appended to `reading-{paper}.md`.

**Next up:** Phase 9.5 — Summary Polish (temperature=0, synthesize retry, staleness tracking), then remaining Phase 9 items (9.1 prompt tuning, 9.6 space control plane), then Phase 10 multimodal. Phase 8 (Search) stays deferred to last — Obsidian already covers human-facing search, and no part of the system needs a search index yet.

---

# Phase 9 Results (cont.) — LLM Provider Abstraction via OpenRouter (9.7)

## What was built

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

## Key decisions

- **One transport, thin providers:** every model is reachable through OpenRouter's OpenAI-compatible chat-completions API, so `base.py` owns streaming + structured JSON exactly once; provider classes only pin identity (name, model normalization). Adding a provider = a 5-line subclass + a registry entry in `PROVIDERS`.
- **Model selection is plug-and-play:** change `model:` in config.yaml (`someorg/luna`, `google/gemini-3.7-flash`, …) — the provider is inferred from the slug; an explicit `provider:` key overrides. No code changes to swap models.
- **Single OPENROUTER_API_KEY:** provider API keys (Google AI Studio, OpenAI, …) don't work against OpenRouter — one OpenRouter key authenticates everything. A per-provider `openrouter_<org>_key` env pattern was built first, then collapsed to the single key once this was understood.
- **Vision removed deliberately:** image input was only ever used by the scanned-PDF OCR fallback; that whole path is deleted ("we will never need image processing"). Audio, if ever needed, would be a separate optional capability on `LLMClient` (OpenRouter accepts audio content parts) — not baked into the text path.
- **Structured output stays schema-driven:** `generate_structured()` injects the JSON schema into the prompt and requests `json_object` mode, falling back to a plain completion and fence-stripping — portable across OpenRouter's heterogeneous models.

## Verified

```
paper-agent status
# → provider: gemini
# → model: google/gemini-3.7-flash
# → API key (OPENROUTER_API_KEY): ✓

# Factory resolution (python)
get_llm_settings() default          → gemini | google/gemini-3.7-flash | OPENROUTER_API_KEY | GeminiClient
config.yaml model: someorg/luna     → openai | someorg/luna | OpenAIClient → https://openrouter.ai/api/v1
config.yaml model: gemini-flash     → gemini | google/gemini-flash (auto-prefixed)

python3 -m compileall paper_agent   ✓
all agent / api / ingestion modules import ✓
```

## Notes

- Restart any running daemon — the stale-daemon lesson applies doubly after an LLM-layer rewrite (`lsof -nP -iTCP:8765`).
- The value in `OPENROUTER_API_KEY` must be an OpenRouter key (`sk-or-v1-…`), not a Google/OpenAI provider key.
- Phase 10 (Multimodal Asks) design notes in phase-plan.md still reference Gemini Vision + `types.Part` — that approach is superseded by the 9.7 architecture (any vision model would go through the OpenRouter transport as an optional capability, same as the audio idea).

---

# Phase 9 Results (Partial) — Reading Threads, Continuity, Chat UI

## What was built

```
paper_agent/
  agent/
    sections.py           # NEW: parse_sections(paper_markdown) — heading-path sections (stack-based; strips * / _ from
                          #   pymupdf4llm's "## **bold**" headings; skips code blocks)
                          #   find_section(paper_markdown, selected_text) → full heading path for a selection.
                          #     normalize(): punctuation-insensitive (strips non-alphanumerics), rejoins hyphenated line
                          #     breaks ("atten-\ntion"), folds Unicode ligatures (ﬁ→fi etc.) + quote/dash variants.
                          #     Tries full selection, then an 80-char probe from the start. "" on no match.
                          #   deepest(path) → last segment for display ("3.3 Position-wise Feed-Forward Networks")
    ask.py                # Thread decision after paper resolution: current section from selection, last 5 turns
                          #   (THREAD_HISTORY_TURNS = 5) from the reading file, _should_continue() decides follow-up vs
                          #   fresh. Continuing injects prior Q&A as "**Earlier in this conversation:**" turns.
                          #   fresh flag bypasses history (param / POST /ask body field / CLI --fresh).
                          #   Section inheritance when continuing without a section match (thread event + saved entry).
                          #   No URL + no selection → last active paper (global rule, incl. CLI).
                          #   New pre-token SSE events: resolved {space, paper} + thread {section, continued}.
                          #   Cross-space retarget to the owning space via find_paper_anywhere().
  ingestion/
    pipeline.py           # + find_paper_anywhere(url, prefer_space=None) — cross-space URL lookup → (space, paper_id);
                          #   prefers the requested space on multi-match
  llm/
    prompts.py            # + conversation_history in build_user_prompt(); continuity sentence in system prompt
  session/
    writer.py             # Reading sessions: paper-resolved Q&A appends to ONE file sessions/reading-{paper-slug}.md
                          #   (frontmatter: paper, reading_session: true, started_at, qa_count — updated each append,
                          #   source_url). Each entry stores a **Section:** heading path. Non-paper asks keep the
                          #   dated-file + AI-slug path; the slug LLM call is SKIPPED for reading sessions.
                          #   + reading_session_path(space, paper_id)
    reader.py             # + section field parsing; get_recent_qa_for_paper(space, paper_id, n) — reading file first,
                          #   legacy dated files fallback via paper_id; + get_session_by_filename()
  api/
    server.py             # + GET /api/spaces/{name}/session-files/{filename} (path-traversal-guarded) — reading files
                          #   have no date. + POST /api/resolve — thread-state preview (no side effects, no LLM).
                          #   + fresh field on POST /ask body
  cli.py                  # + paper-agent ask --fresh
raycast-extensions/paper-agent/src/
  ask.tsx                 # REWRITE: chat-style single window — Composer (Form) ↔ ThreadView (Detail with accumulating
                          #   markdown transcript + streaming answer), no navigation-stack growth. Hotkey always lands
                          #   on the Composer (WhatsApp-style). Thread status line (● continuing §X — N prior Q&A /
                          #   ○ fresh thread / ○ new paper / ○ no paper + forced-fresh variant), History (last 5 Q&A),
                          #   "Replying to §X" quote. Keys: ⏎ send · ⌘N Force New Thread · ⌘H View Full Thread ·
                          #   ⌘R Refresh Selection (re-captures AND re-runs the resolve preview) · ⇧⌘P Change Paper….
                          #   On mount / ⌘R: POST /api/resolve → hydrate space, resolved paper, seed turns from
                          #   recent_qa. Paper dropdown + LS_LAST_PAPER removed — server resolves the paper from the
                          #   URL; space follows paper.
  session-history.tsx     # Reading files render as "title (reading)" with "ongoing" date, open via session-files endpoint
```

## Key decisions

- **The vault IS the conversation state:** continuity is stateful server-side — `ask()` loads the last 5 turns from the reading file; the client never sends `conversation_history` (resolves the plan's stateless-vs-stateful open question).
- **Section-based continuation:** `_should_continue()` fallback ladder — no prior turns → fresh; no selection → continue; selection not found in paper.md → continue (same-paper rule); different section → fresh. Section inheritance keeps the chain alive when continuing without a match (inherited section shown in the `thread` event and stored in the saved entry — a later same-section selection still continues).
- **Reading sessions are automatic, not a toggle (9.4):** per-paper grouping keyed by resolved paper / source_url — all Q&A for a paper appends to one `reading-{paper-slug}.md` with `qa_count` frontmatter updated per append. Simpler than the plan's "reading-mode flag". The slug LLM call is skipped — one less Gemini call per question.
- **Server-resolved paper; space follows paper:** the Raycast Paper dropdown + `LS_LAST_PAPER` were removed — they silently overrode URL-based resolution (reading paper B could ground answers in paper A). The client sends only `{question, selected_text, source_*}`; explicit `paper_id` only via the "Change Paper…" override picker (⇧⌘P), needed for URL-less contexts like PDFs in Preview. The space dropdown is only the ingest target for unknown URLs; on resolve the space switches to the owning space.
- **Cross-space URL lookup:** `find_paper_anywhere(url, prefer_space)` → `(space, paper_id)`; `ask()` retargets to the owning space — no duplicate ingestion into the wrong space.
- **Preview endpoint rationale:** the composer must show ●/○ BEFORE the user asks, but the decision needs paper.md which lives server-side — so `POST /api/resolve` pre-runs the identical `find_section` + `_should_continue` logic (no side effects, no LLM). It's recomputed on send, so the label can never lie.
- **Last-active-paper fallback is global:** no URL + no selection → `context.get_active_paper_id()` (requested space, then `last_space`) — includes the CLI; a bare `paper-agent ask "..."` continues the last paper's thread (escapes: `--fresh`, any `--selected` text, or `--paper`).
- **Chat-style Raycast UI:** one window, Composer ↔ ThreadView; hotkey always lands on the Composer (WhatsApp-style); ⏎ "Ask Follow-up" returns to the composer; follow-up action hidden while streaming.

## API endpoints (Phase 9 additions)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/resolve` | Thread-state preview. Body `{source_url, selected_text, space?}` → `{found, space, paper_id, title, qa_count, recent_qa (last 10 with sections), thread_state: continuing\|fresh\|new_paper\|no_paper, section}`. No side effects, no LLM; runs the exact same `find_section` + `_should_continue` logic as `ask()`. No URL + no selection → active paper (mirrors ask()); selection but no URL → `no_paper` |
| `GET` | `/api/spaces/{name}/session-files/{filename}` | Read a session file by filename (path-traversal-guarded) — reading-session files have no date |
| `POST` | `/api/spaces/{name}/ask` | + `fresh` body field — bypass conversation history (force a new thread). + pre-token `resolved` and `thread` SSE events |

## CLI additions

| Command | Description |
|---------|-------------|
| `paper-agent ask ... --fresh` | Bypass conversation history (force a new thread) |

## Verified

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

## Notes for next phase (Phase 9.5 + remaining Phase 9)

- **Naming collision warning:** Phase 9.5 the PHASE = "Summary + Synthesis Polish" (temperature=0, synthesize retry, staleness tracking, JSON storage consistency) — still NOT started. Idea 9.5 inside Phase 9 = "Conversation continuity" — DONE this session. Don't conflate the two.
- Remaining Phase 9: 9.1 prompt tuning (design notes in phase-plan.md), 9.6 space control plane (`spaces.tsx` doesn't exist; `POST /api/spaces` not built). 9.2 dropped (space follows paper — only a brand-new topic space needs the terminal, which is rare and deliberate); 9.3 covered (session-history command + ⌘H thread view; Obsidian for long-form).
- **Daemon cwd requirement:** the daemon must be started from the project root — it discovers `.env` (now `OPENROUTER_API_KEY`; was `GEMINI_API_KEY` before 9.7) via cwd (python-dotenv); started elsewhere it returns "OPENROUTER_API_KEY is not set. Add it to your .env file.".
- **Stale-daemon lesson:** a 9-day-old daemon was silently serving old code on port 8765 (masked by a failed redirect) and caused confusing verification results until killed. Check `lsof -nP -iTCP:8765` when behavior seems stale.
- **pymupdf4llm heading mangling:** sometimes drops headings into garbled figure text (the Attention paper lost §3.1/§3.2) → section matches land on the nearest surviving heading; verbatim selections match, paraphrases don't.
- **Vault cleanup:** ~10 test Q&A entries left in the research vault from verification.

---

# Phase 7 Results — Summaries + Knowledge Compounding

## What was built

```
paper_agent/
  agent/
    summarize.py          # Per-paper: reads Q&A sessions → structured Gemini → summary.md + metadata.yaml
    synthesize.py         # Cross-paper: reads all summaries → structured Gemini → cross-paper-insights.md + synthesis.json
    knowledge.py          # Space-level: update_knowledge() → knowledge.md, update_open_questions() → open-questions.md
    __init__.py           # Shared PaperAgentError (consolidated from 3 separate definitions)
  llm/
    prompts.py            # +SUMMARY_SCHEMA, SYNTHESIS_SCHEMA, KNOWLEDGE_SCHEMA, OPEN_QUESTIONS_SCHEMA
                           # +build_summarize_prompt(), build_synthesize_prompt(), build_knowledge_prompt(), build_open_questions_prompt()
  vault.py                # +regenerate_index(space) — full index rebuild from vault state
                           # +_parse_session_filename(), _count_questions() helpers
  session/writer.py       # Replaced _update_index() with regenerate_index() call
  api/server.py           # +POST /summarize, POST /synthesize, POST /knowledge, POST /open-questions
  cli.py                  # +summarize, synthesize, knowledge, open-questions commands
raycast-extensions/paper-agent/src/
  end-paper.tsx           # +KnowledgeView, OpenQuestionsView components
                           # +⌘K Update Knowledge, ⌘O Open Questions actions in SummaryView and SynthesisView
```

## Key decisions

- **Summarize = what you learned, not what the paper says:** The summary schema captures themes (explored, learned, surprise, so_what), open threads, gaps, and biggest takeaway — all grounded in your Q&A history, not the paper's abstract.
- **Structured Gemini calls:** `generate_structured()` with response schemas ensures consistent JSON output. Summary JSON stored in `metadata.yaml` under `summary` key — this is the handoff to synthesize.
- **Synthesize reads summaries, not papers:** Cross-paper insights are built from the compact structured summaries in `metadata.yaml`, not full papers. This keeps token counts manageable for 50+ papers.
- **knowledge.md = current snapshot:** Overwrites each time. Reflects the latest state of what the space knows. Themes have confidence levels (solid/developing/tentative), key facts are sourced to specific papers.
- **open-questions.md = curated gaps:** Aggregates open_threads + gaps from all summaries. Gemini deduplicates and prioritizes (high/medium/low). Questions are rephrased to be actionable.
- **regenerate_index replaces incremental updates:** Instead of appending lines, the full index is rebuilt from vault state every time something changes. Papers show summary links when available. Knowledge section lists all artifacts.
- **Shared PaperAgentError:** Fixed bug where summarize.py and synthesize.py defined their own PaperAgentError classes — API handler only caught ask.py's version, causing 500s. Consolidated into agent/__init__.py.
- **Summary gate:** Requires ≥5 Q&A to summarize (MIN_QA_FOR_SUMMARY). Prevents shallow summaries from 1-2 quick questions.
- **Synthesize gate:** Requires ≥2 papers with summaries (MIN_PAPERS_FOR_SYNTHESIS).
- **Knowledge gate:** Requires ≥1 summarized paper (MIN_PAPERS_FOR_KNOWLEDGE).

## Vault shape (updated)

```
~/.paper-vault/
  spaces/
    {name}/
      papers/
        {paper-slug}/
          paper.md
          metadata.yaml     # +summary (structured JSON from summarize)
          summary.md        # agent-written summary (new)
      sessions/
      summaries/
        cross-paper-insights.md   # cross-paper connections (new)
        synthesis.json             # raw structured JSON (new)
      knowledge.md                 # space-level knowledge map (new)
      open-questions.md            # prioritized open questions (new)
      index.md                     # auto-regenerated: papers + sessions + knowledge links
```

## API endpoints (Phase 7 additions)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/spaces/{name}/summarize` | Summarize paper Q&A → `summary.md`. Body: `{paper_id}` |
| `POST` | `/api/spaces/{name}/synthesize` | Cross-paper synthesis → `cross-paper-insights.md` |
| `POST` | `/api/spaces/{name}/knowledge` | Update space knowledge → `knowledge.md` |
| `POST` | `/api/spaces/{name}/open-questions` | Curate open questions → `open-questions.md` |

## CLI commands (Phase 7 additions)

| Command | Description |
|---------|-------------|
| `paper-agent summarize --space <name> --paper <paper_id>` | Distill Q&A insights for a paper |
| `paper-agent synthesize --space <name>` | Find cross-paper connections |
| `paper-agent knowledge --space <name>` | Build space-level knowledge map |
| `paper-agent open-questions --space <name>` | Curate prioritized open questions |

## Verified

```
# CLI — full knowledge loop
paper-agent summarize --space research --paper attention-is-all-you-need
# → Summary written (3 themes, 2 open threads, 2 gaps)

paper-agent summarize --space research --paper eagle-efficient-training-free-router-for-multi-llm-inference
# → Summary written (3 themes, 3 open threads, 2 gaps)

paper-agent synthesize --space research
# → Cross-paper insights written (2 connections)

paper-agent knowledge --space research
# → Knowledge written (3 themes, 5 key facts)

paper-agent open-questions --space research
# → Open questions written (9 questions: 6 high, 3 medium, 0 low)

# API — all 4 endpoints
POST /api/spaces/research/summarize   → status=ok themes=2 open_threads=4 gaps=3
POST /api/spaces/research/synthesize  → status=ok connections=1
POST /api/spaces/research/knowledge   → status=ok themes=3 key_facts=6
POST /api/spaces/research/open-questions → status=ok questions=12

# Error cases
POST /api/spaces/nonexistent/knowledge     → 404
POST /api/spaces/research/summarize {bad}  → 400 "Paper not found"
POST /api/spaces/research/summarize {no QA} → 400 "Only 0 Q&A found, need at least 5"

# index.md — auto-regenerated with papers, sessions, knowledge sections
# Papers with summaries show [summary] link, papers without don't

# Raycast
npx tsc --noEmit                         ✓ (0 errors)
npm run build                            ✓ (4 entry points compiled)
```

## Raycast flow

```
End Paper form → SummaryView
  ⌘S → SynthesisView
    ⌘K → KnowledgeView
      ⌘O → OpenQuestionsView
    ⌘O → OpenQuestionsView
  ⌘K → KnowledgeView
  ⌘O → OpenQuestionsView
```

## Notes for next phase (Phase 8)

- Phase 8 needs: text + semantic search across papers, sessions, summaries
- All markdown files are in the vault — text search can walk the tree
- `metadata.yaml` has structured data for indexed search
- `summary` field in metadata has structured themes/facts for semantic search
- API endpoint to add: `GET /api/spaces/{name}/search?q=...`
- Phase 9.5 (Summary Polish) already documented in phase-plan.md — temperature=0, synthesize retry, staleness tracking, JSON storage consistency

---

# Phase 6 Results — PDF Ingestion

## What was built

```
paper_agent/
  ingestion/
    __init__.py
    pdf_converter.py     # pymupdf4llm: PDF → (markdown, title). Title from first H1 in markdown.
    fallback.py          # Gemini Vision: scanned PDF → markdown. Batched 10 pages/request, 150 DPI.
    html_extractor.py    # trafilatura + httpx: URL/HTML → (markdown, title). Blogs, articles, docs.
    downloader.py        # httpx async download. arxiv abs→pdf normalization. Content-type detection.
    pipeline.py          # ingest(space, source) → download → convert/extract → fallback → save to vault.
                         # find_paper_by_url(space, url) → checks metadata.yaml for matching URL or arxiv ID.
  vault.py               # + list_papers(), get_paper_path(), get_paper_metadata()
                         # + purge_space(), delete_space() (secret-protected)
  config.py              # + get_secret_key() for PAPER_AGENT_SECRET
  llm/prompts.py         # + paper_content/paper_title params in build_user_prompt()
  agent/ask.py           # + paper_id param, auto-ingestion from source_url, paper.md injection
  api/server.py          # + POST/GET /api/spaces/{name}/papers, DELETE endpoints (purge, delete-space)
                         # Wired body.paper_id → run_ask()
  cli.py                 # + ingest command, --paper flag on ask, purge + delete-space commands
raycast-extensions/paper-agent/src/
  ask.tsx                # + Paper dropdown, ingestion status events in SSE, paper_id passthrough
```

## Key decisions

- **pymupdf4llm (not docling/marker):** Lightweight (~50MB), sub-second, serverless-friendly. Built-in Tesseract OCR for partially scanned pages. Gemini Vision fallback for truly scanned PDFs (~$0.05/60pg, rare).
- **No PDF stored in vault:** Only `paper.md` + `metadata.yaml`. PDF is a temp file during conversion, deleted after. `source_url` in metadata allows re-download.
- **Auto-ingestion in ask flow:** No separate hotkey. When `source_url` is provided and paper isn't cached, daemon auto-downloads and converts before answering. Status events flow through SSE to Raycast.
- **URL-based ingestion:** arxiv abs→pdf normalization. HTML pages via trafilatura (blogs, articles). Twitter deferred.
- **Paper slug from title:** Extracted from first H1 in converted markdown, slugified. Zero cost. Falls back to filename.
- **Full paper context:** Entire `paper.md` injected into prompt. No truncation. Smart context deferred to Phase 9.
- **Explicit paper selection:** `ask()` requires `paper_id` or `source_url` for paper context. No silent fallback to `active_paper_id`.
- **Secret-protected destructive ops:** `purge` and `delete-space` require `PAPER_AGENT_SECRET` from `.env`. API uses `X-Paper-Agent-Secret` header. `delete-space` refuses if non-empty.
- **Dependencies added:** pymupdf4llm, python-multipart, httpx, trafilatura, lxml_html_clean

## Vault shape (updated)

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

## API endpoints (Phase 6 additions)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/spaces/{name}/papers` | List papers with metadata |
| `POST` | `/api/spaces/{name}/papers` | Ingest from `{url}` form field or multipart file upload |
| `DELETE` | `/api/spaces/{name}/contents` | Purge all space contents (requires `X-Paper-Agent-Secret`) |
| `DELETE` | `/api/spaces/{name}` | Delete space — only if empty (requires `X-Paper-Agent-Secret`) |

## CLI commands (Phase 6 additions)

| Command | Description |
|---------|-------------|
| `paper-agent ingest --space <name> [--url URL \| <pdf_path>]` | Ingest a paper from URL or local file |
| `paper-agent ask ... --paper <paper_id>` | Ask with explicit paper context |
| `paper-agent purge --space <name> --secret <key>` | Delete all contents of a space |
| `paper-agent delete-space --space <name> --secret <key>` | Delete a space (must be empty) |

## Verified

```
# CLI ingest from URL
paper-agent ingest --space research --url https://arxiv.org/abs/1706.03762
# → Ingested: Attention Is All You Need (15 pages, pymupdf4llm)

# CLI ingest from local file
paper-agent ingest --space research ~/Downloads/paper.pdf
# → Ingested: Eagle: Efficient Training-Free Router... (8 pages)

# CLI ask with explicit paper
paper-agent ask "what is the key innovation?" --space research --paper attention-is-all-you-need
# → Answer grounded in full 15-page paper

# CLI ask with auto-find from URL (cached)
paper-agent ask "what is attention?" --space research --source-url https://arxiv.org/abs/1706.03762
# → Finds cached paper → answer grounded in full paper

# CLI ask with auto-ingestion (new URL)
paper-agent ask "what is this paper about?" --space research --source-url https://arxiv.org/abs/2409.15518
# → [Downloading and converting paper...]
# → [ingested]
# → Answer grounded in full Eagle paper

# HTML ingestion (blog post)
paper-agent ingest --space research --url https://lilianweng.github.io/posts/2023-03-15-prompt-engineering/
# → Ingested: Prompt Engineering (html, trafilatura)

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

# Raycast
npx tsc --noEmit                         ✓ (0 errors)
npm run build                            ✓ (3 entry points compiled)
```

## Notes for next phase (Phase 7)

- Phase 7 needs: paper summaries, `knowledge.md`, cross-paper synthesis
- `paper.md` available for Gemini to read and summarize
- `metadata.yaml` has all paper metadata for indexing
- Session files have Q&A history that can feed into summaries
- API endpoints to add: `POST /api/spaces/{name}/summarize`, `POST /api/spaces/{name}/synthesize`

---

# Phase 5 Results — Raycast Hotkey

## What was built

```
raycast-extensions/paper-agent/
├── package.json                  # Raycast extension config, 3 commands, preferences
├── tsconfig.json                 # TypeScript strict config
├── raycast-env.d.ts              # Raycast environment types
└── src/
    ├── capture-and-ask.tsx       # no-view hotkey entry: captures selection fresh, launches ask
    ├── capture.ts                # Shared captureContext() + Source type (getSelectedText + AppleScript fallbacks)
    ├── ask.tsx                   # View command: space picker, question form, SSE streaming answer
    └── session-history.tsx       # Browse past sessions by space → date → Q&A detail
```

## Key design decisions

- **Three commands:** `Capture & Ask Paper Agent` (no-view hotkey entry, always fresh), `Ask Paper Agent` (view form, receives launchContext), and `Paper Agent Sessions` (browse history)
- **No-view entry command:** `capture-and-ask` runs fresh on every hotkey press. `getSelectedText()` and AppleScript fallbacks execute before the UI mounts. Passes `{selectedText, raycastRawText, source, invocationId}` to the `ask` command via `launchCommand({ type: LaunchType.UserInitiated, context })`.
- **Stale-selection fix:** Raycast view-mode commands are kept alive between invocations — `useEffect([])` only runs once per mount. The no-view entry command solves this by capturing OS state before the view mounts. The view command reads from `launchContext` and never calls `captureContext()` on mount (unless opened manually from Raycast search, in which case it falls back to capture).
- **Selection capture:** Uses `getSelectedText()` + `getFrontmostApplication()` from Raycast API. For Chrome/Safari, also runs AppleScript (`runAppleScript` from `@raycast/utils`) to capture URL and page title. Clipboard fallback (Cmd+C via System Events) for Chrome PDF viewer where `getSelection()` can't reach the PDF.
- **Refresh Selection action:** `⌘R` inside the ask form re-captures selection as a safety valve.
- **Space default priority:** Daemon context API (`GET /api/context` → `last_space`) → Raycast `LocalStorage` (last used) → extension preferences → first space in list
- **Streaming:** Custom SSE parser over `fetch` + `ReadableStream`. Tokens accumulate in a `Detail` component with markdown. `[DONE]` sentinel ends the stream, `session_path` JSON is parsed and displayed as footer
- **Error handling:** Catches daemon-unreachable at init (shows warning), API errors during stream (shows error in detail view), and abort on unmount
- **Session history:** Three-level navigation — Space selector → Session list (slug, date, QA count) → Session detail (full Q&A markdown). Dates shown in ISO → locale-formatted
- **Form state:** Space dropdown uses `storeValue` for Raycast persistence. Question text area auto-focuses. "Show selected text" checkbox toggles visibility of captured text.
- **Server-side logging:** `ask_api` endpoint logs `space`, `question`, `selected_text`, and source metadata to terminal for debugging.

## API endpoints consumed

| Method | Path | Used by |
|--------|------|---------|
| `GET` | `/api/spaces` | Ask form (dropdown), Session history (space selector) |
| `POST` | `/api/spaces/{name}/ask` | Ask form submit → SSE streaming in detail view |
| `GET` | `/api/spaces/{name}/sessions` | Session history → list view |
| `GET` | `/api/spaces/{name}/sessions/{date}` | Session history → detail view |
| `GET` | `/api/context` | Ask form init (default space from last_space) |

## Extension preferences

| Name | Type | Default | Purpose |
|------|------|---------|---------|
| `daemonUrl` | textfield | `http://localhost:8765` | Daemon base URL |
| `defaultSpace` | textfield | (empty) | Fallback space if no context/previous |

## Verified

```
# Daemon API — all endpoints responding
curl localhost:8765/api/health            → {"status":"ok","version":"0.1.0"}
curl localhost:8765/api/spaces            → [{"name":"research","sessions":5}]
curl localhost:8765/api/context           → {last_space:"research", ...}
curl localhost:8765/api/spaces/research/sessions → 5 sessions with slug/date/qa_count
CORS: localhost allowed, external blocked

# TypeScript — compiles clean, Prettier formatted
npx tsc --noEmit                         ✓ (0 errors)
npm run build                            ✓ (3 entry points compiled)
npm install                              ✓ (198 packages)

# Stale-selection fix verified:
# Select text A → hotkey → form shows text A
# Close form → select text B → hotkey → form shows text B (not stale A)
# Repeated invocations always show fresh selection
```

## Hotkey setup (user action required)

1. Run `npm run dev` from `raycast-extensions/paper-agent/`
2. In Raycast → Extensions → Paper Agent → **"Capture & Ask Paper Agent"** → set hotkey (e.g. `Cmd+Shift+P`)
3. Ensure the daemon is running: `paper-agent serve`

## Daily loop

```
Select text in Chrome/Safari/any app → Cmd+Shift+P → pick space → type question → Enter → streamed markdown answer → auto-saved to vault
```

## Notes for next phase (Phase 6)

- ✅ Phase 6 complete — PDF ingestion, auto-ingest in ask flow, Raycast paper picker
- `paper_agent/ingestion/` module built with pymupdf4llm + trafilatura + Gemini Vision fallback
- `POST /api/spaces/{name}/papers` and `GET /api/spaces/{name}/papers` endpoints added
- `paper-agent ingest` CLI command added
- `ask()` now injects `paper.md` when `paper_id` or `source_url` is provided
- Raycast ask form has paper dropdown + ingestion status events in SSE stream

---

# Phase 4 Results — Minimal Daemon API (HTTP + SSE)

## What was built

```
paper_agent/
├── api/
│   ├── __init__.py              # (empty)
│   └── server.py                # FastAPI app: 7 endpoints, CORS for localhost, SSE streaming
├── daemon.py                    # Replaced sleep stub → uvicorn startup (accepts reload param)
└── cli.py                       # Updated serve command: added --reload flag
```

## Key decisions (from user)

- **SSE format:** Plain text `data: <token>\n\n` per token, terminal `data: [DONE]\n\n`, then `data: {"session_path": "..."}\n\n` for session confirmation
- **Auto-save on API ask:** Same as CLI — Q&A saves automatically after streaming completes (no separate save call needed)
- **Session by date JSON:** Returns parsed Q&A list (same format as `_parse_session_file`)
- **Context PUT:** Partial merge (only updates provided fields, matches `context.update_context()` behavior)
- **CORS:** Regex-based — allows `http://localhost:*` and `http://127.0.0.1:*`, blocks all other origins
- **File organization:** `daemon.py` imports and starts FastAPI app from `api/server.py` via uvicorn
- **--reload flag:** Added for development (passes `reload=True` to uvicorn)
- **Date format:** API accepts ISO dates (`2026-05-03`), converts to compact (`20260503`) internally for `get_session_by_date`

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | `{"status": "ok", "version": "0.1.0"}` |
| `GET` | `/api/spaces` | `[{"name": "ml-research", "sessions": 3}]` |
| `POST` | `/api/spaces/{name}/ask` | JSON body `{question, selected_text?, ...}` → SSE token stream → `[DONE]` → `{session_path}` |
| `GET` | `/api/spaces/{name}/sessions` | List sessions with slug, date, QA count, modified time |
| `GET` | `/api/spaces/{name}/sessions/{date}` | Parsed Q&A list (accepts ISO dates like `2026-05-03`) |
| `GET` | `/api/context` | Full context: last_space, last_source_*, active_paper_id, last_session_file |
| `PUT` | `/api/context` | Partial update context (merge with existing) |

## Verified

```
paper-agent serve
# → http://localhost:8765 alive with Uvicorn

curl localhost:8765/api/health
# → {"status":"ok","version":"0.1.0"}

curl localhost:8765/api/spaces
# → [{"name":"research","sessions":5}]

curl -N -X POST localhost:8765/api/spaces/research/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"what is an attention head?","selected_text":"Multi-head attention allows...","source_app":"Chrome","source_title":"Attention Is All You Need","source_url":"https://arxiv.org/abs/1706.03762"}'
# → data: Based on the text...
# → data: [DONE]
# → data: {"session_path":"/Users/.../attention-heads-20260504.md"}

curl localhost:8765/api/spaces/research/sessions
# → [{file, path, qa_count, slug, date, modified}, ...]

curl localhost:8765/api/spaces/research/sessions/2026-05-03
# → [{id:"Q1", question:"...", answer:"...", context:"", source:"...", file:"..."}]

curl localhost:8765/api/context
# → {last_space, last_source_url, last_source_title, last_source_app, active_paper_id, last_session_file}

curl -X PUT localhost:8765/api/context -H "Content-Type: application/json" -d '{"space":"new-space"}'
# → {"status":"ok"}

curl -s -I -X OPTIONS localhost:8765/api/spaces -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: GET" | grep access-control
# → access-control-allow-origin: http://localhost:3000 (CORS working)

curl -s -I -X OPTIONS localhost:8765/api/spaces -H "Origin: https://example.com" \
  -H "Access-Control-Request-Method: GET" | grep access-control
# → (no CORS headers — non-localhost blocked)

cat ~/.paper-vault/spaces/research/sessions/attention-heads-20260504.md
# → YAML frontmatter + Q&A with Context + Source + A preserved

paper-agent serve --help
# → --port / --reload flags present
```

## Notes for next phase (Phase 5)

- ✅ Phase 5 complete — Raycast extension project built at `raycast-extensions/paper-agent/`
- Daemon API fully operational — ready to be called from Raycast fetch + ReadableStream
- `context` API endpoints ready for Raycast to intelligently default space/source
- `sessions` API ready for session history browsing in Raycast
- SSE streaming endpoint tested — Raycast can consume ReadableStream directly

---

# Phase 3 Results — Session Persistence

## What was built

```
paper_agent/
├── session/
│   ├── __init__.py
│   ├── writer.py              # save_qa() — AI slug generation (Gemini) + heuristic fallback
│   │                          #   creates/appends {slug}-YYYYMMDD.md with YAML frontmatter
│   │                          #   auto-creates space index.md on first session write
│   └── reader.py              # get_history(space, n=5), list_sessions(), get_session_by_date()
├── context.py                 # Read/write active context to .paper-agent/context.yaml
│                              #   last_space, last_source_*, last_session_file, active_paper_id
└── agent/
    └── ask.py                 # Updated: buffers streaming response, auto-saves Q&A after stream
```

## Key decisions (from user)

- **Session filenames:** `{slug}-YYYYMMDD.md` — slug generated by AI (Gemini Flash prompt), falls back to heuristic from source_title or question
- **Slug generation:** Launched in parallel with answer streaming via `asyncio.create_task`. Both AI and heuristic attempt to produce 2-4 word hyphenated slugs
- **Session file format:** YAML frontmatter (space, model, date, slug) + `### Q1` blocks with `**Q:**`, `**Context:**`, `**Source:**`, `**A:**` — same-day same-slug appends as Q2, Q3...
- **Buffering:** `ask()` buffers all tokens while streaming, then calls `save_qa()` with full answer text after the generator loop completes. Save happens before `StopAsyncIteration` so the caller (CLI) sees it after the `async for` loop.
- **Save confirmation:** Prints full file path (e.g. `Saved to ~/.paper-vault/spaces/research/sessions/transformer-ml-20260503.md`)
- **Context storage:** `~/.paper-vault/.paper-agent/context.yaml` — lightweight YAML, temporary until Phase 4 daemon API picks it up
- **index.md:** Auto-created in space root on first session write, appended with timestamp + Q count on each save

## Verified

```
paper-agent ask "what is a transformer in ML?" --space research \
  --source-title "Attention Is All You Need" --source-url "https://arxiv.org/..."
# → streaming answer
# → "Saved to ~/.paper-vault/spaces/research/sessions/transformer-ml-20260503.md"

cat ~/.paper-vault/spaces/research/sessions/transformer-ml-20260503.md
# → YAML frontmatter + Q&A block with Context, Source, A

cat ~/.paper-vault/spaces/research/index.md
# → Session list with links and timestamps

paper-agent ask "explain this" --space research \
  --selected "Attention(Q,K,V) = softmax(QK^T/√dk)V" \
  --source-app Chrome --source-title "Attention Is All You Need" \
  --source-url "https://arxiv.org/abs/1706.03762"
# → Context block preserved in session file

python -c "from paper_agent.session.reader import get_history; print(get_history('research', n=2))"
# → [{'id': 'Q1', 'question': '...', 'answer': '...', 'context': '...', ...}]

python -c "from paper_agent import context; print(context.get_last_space())"
# → research
```

## Notes for next phase (Phase 4)

- Phase 4 needs: FastAPI server (`paper_agent/api/server.py`), SSE streaming endpoints
- `context.py` ready for daemon API (`GET /api/context`, `PUT /api/context`)
- `session/reader.py` ready for `GET /api/spaces/{name}/sessions`
- `session/writer.py` ready for auto-save via API (same `save_qa()` call)
- Daemon stub `daemon.py` needs to start FastAPI + uvicorn

---

# Phase 2 Results — Ask (No PDF Required)

## What was built

```
paper_agent/
├── llm/
│   ├── __init__.py
│   ├── gemini.py            # Async streaming client (google-genai SDK, client.aio)
│   └── prompts.py           # System prompt + user prompt with selected text + source metadata
├── agent/
│   ├── __init__.py
│   └── ask.py               # Orchestration: validate space, check API key, build prompts, stream
└── cli.py                   # Updated: paper-agent ask "question" --space ... --selected ...
```

## Key decisions (from user)

- **Source metadata:** Included in the prompt so Gemini can ground answers in where the text came from
- **Space validation:** Fails early with helpful error ("Create it with: paper-agent init --space ...")
- **Streaming display:** Tokens printed inline in terminal (natural streaming feel)
- **Prompt format:** Selected text appears as blockquote (`> text`), source as separate line, question clearly marked
- **Async SDK quirk:** `client.aio.models.generate_content_stream` returns a coroutine → must `await` it first, then iterate

## Verified

```
paper-agent ask "what is a transformer?" --space research
# → "In the context of academic papers... A Transformer is a powerful deep learning architecture..."

paper-agent ask "explain this concept" --space research \
  --selected "self-attention computes weighted sums of values" \
  --source-app Chrome \
  --source-title "Attention Is All You Need" \
  --source-url "https://arxiv.org/abs/1706.03762"
# → "In the context of self-attention: Values: Imagine your input data..."

paper-agent ask "what is attention?" --space nonexistent
# → Error: Space 'nonexistent' does not exist. Create it with: paper-agent init --space nonexistent
```

## Notes for next phase (Phase 3)

- Phase 3 needs: session persistence (`paper_agent/session/writer.py`, `reader.py`)
- Need to create: `paper_agent/session/writer.py` — auto-save Q&A to dated session file
- Need to create: `paper_agent/session/reader.py` — `get_history(space, n=5)`
- Need to create: `paper_agent/context.py` — lightweight active context
- Wire into `ask()`: after streaming completes, auto-save Q&A
- Space `index.md` — auto-create with list of sessions + timestamps

---------------------------------------------------------

# Phase 1 Results — Scaffold + Vault + Spaces

## What was built

```
pdf-reader/
├── pyproject.toml
├── phase-plan.md
├── paper_agent/
│   ├── __init__.py          # __version__ = "0.1.0"
│   ├── cli.py               # Click group: init, status, serve
│   ├── config.py            # Loads config.yaml + .env (python-dotenv)
│   ├── vault.py             # Create/list spaces in ~/.paper-vault/
│   └── daemon.py            # Stub: prints port, sleeps (no HTTP yet)
└── outputs.md               # This file
```

Old `frontend/`, `backend/`, `plan.md`, `PRD.md`, `starter_prompt.md` moved to `/tmp/paper-agent-legacy/`.

## Key decisions (from user)

- **Python:** >=3.11
- **CLI:** `paper-agent init --space <name>` — creates vault + space in one shot
- **Spaces:** Directories only on init (`papers/`, `sessions/`, `summaries/`). No stub `.md` files.
- **API key:** Loaded from `.env` (cwd or `~/.paper-vault/.paper-agent/.env`) via python-dotenv. Env var: `GEMINI_API_KEY`.
- **Model default:** `gemini-2.5-flash` in `config.yaml` (user wanted "gemini 3.0 flash" but that ID doesn't exist — easy to change in config)
- **Google SDK:** `google-genai` (the newer unified SDK, not `google-generativeai`)
- **Daemon in Phase 1:** Sleep stub only. FastAPI/SSE added in Phase 4.
- **Spaces discovery:** Scan `~/.paper-vault/spaces/` directory

## Vault shape

```
~/.paper-vault/
├── .paper-agent/
│   └── config.yaml          # vault_path, model
└── spaces/
    └── {name}/
        ├── papers/          # empty dir
        ├── sessions/        # empty dir
        └── summaries/       # empty dir
```

## Verified

```
pip install -e .                    ✓
paper-agent --help                  ✓ (init, status, serve)
paper-agent init --space ml-research  ✓ (vault + space tree created)
paper-agent status                  ✓ (path, spaces, model, key status)
paper-agent serve                   ✓ (prints port, stays alive, Ctrl+C exits)
```

## Dependencies (pyproject.toml)

click, pyyaml, google-genai, fastapi, uvicorn, sse-starlette, python-dotenv
