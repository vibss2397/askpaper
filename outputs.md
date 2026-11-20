# Project Status — paper-agent

## Where we are

| Phase | Status | What works |
|-------|--------|------------|
| 1 — Scaffold + Vault + Spaces | ✅ Done | `paper-agent init/status/serve`, vault tree, config |
| 2 — Ask (No PDF) | ✅ Done | CLI `paper-agent ask` streams Gemini answers with selected-text context |
| 3 — Session Persistence | ✅ Done | Q&A auto-saved to dated session files, `index.md`, context tracking |
| 4 — Daemon API (HTTP + SSE) | ✅ Done | FastAPI server, 7 endpoints, CORS, SSE streaming |
| 5 — Raycast Hotkey | ✅ Done → retired | Retired at the Phase 6 cutover: extension deleted from the repo and from the Raycast app; the Swift panel app (5R) is the primary and only UI |
| 5R — UI Rewrite: Swift Panel App | ✅ Cutover done | Native menu-bar panel app (default ⌃A, ⌘⇧P available post-Raycast) with full Raycast ask-flow parity: OS capture ladder, web page in a vibrancy WKWebView, streaming answers. Phase 6 cutover complete: Raycast extension deleted (rollback = restore from git history). See "Swift Panel App Migration" section below |
| 6 — PDF Ingestion | ✅ Done | PDF/HTML ingestion, auto-ingest in ask, paper-aware answers, Raycast paper picker |
| 7 — Summaries + Knowledge | ✅ Done | Paper summaries, `knowledge.md`, `open-questions.md`, cross-paper synthesis, enhanced `index.md` |
| 8 — Search | ⏸️ Deferred to last | Obsidian covers find; no consumer needs a search index yet |
| 9 — Desktop Polish | 🟡 Partial | 9.4 loop mode + 9.5 continuity + 9.7 LLM provider abstraction done (reading threads, section-based follow-ups, chat-style Raycast UI, any-model-via-OpenRouter); remaining: 9.1 prompt tuning, 9.6 space control plane; 9.2 dropped, 9.3 covered |
| 9.5 — Summary Polish | ✅ Done | One-vs-rest forced-verdict synthesize (no empty bail-outs), all calls on gpt-5.6-luna @ low reasoning, summary.json sidecar + staleness tracking everywhere |
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

**Next up (agreed order):** ~~1–5~~ DONE (key replaced; Safari selection capture enabled; Zen decision dropped — the AX title/arXiv-ID fallback + allowlisted ⌘C cover it; Phase 5 polish trimmed to what shipped: hotkey presets, full-fidelity clipboard restore, turn cards, load-retry — launch-at-login, app icon, daemonUrl UI, window growth consciously skipped; Phase 6 cutover executed: ⌘⇧P on Swift, Raycast extension deleted from repo + Raycast app, docs updated). Remaining: 6) 9.1 prompt tuning + 9.6 space control plane (needs a web-page redesign, not Raycast); 7) Phases 10–14. Phase 8 (Search) stays deferred to last — Obsidian already covers human-facing search, and no part of the system needs a search index yet.

---

# Swift Panel App Migration — Results (Phases 0–4, Raycast → native panel UI)

Tracking doc: **`paper-agent-swift-app/migration_plan.md`** — the single source of truth for the migration (read it top to bottom before touching Swift code). Status: **Phases 0–6 COMPLETE — cutover executed.** The Raycast extension was deleted from the repo and removed from the Raycast app at cutover (rollback = restore from git history and rebind). The Swift app's hotkey default stays **⌃A** (user preference; ⌘⇧P remains selectable in the Hotkey menu). Post-cutover hardening that shipped with the cutover: redacted ASK logging (lengths only), sanitizer scheme-check hardening, page-driven Escape (picker-first, then panel hide), native load-retry after a failed preload, full-fidelity clipboard snapshot/restore with changeCount detection, ⌘C fallback allowlisted to browser/PDF apps, AppleScript 3 s timeout, hotkey debounce, turn-card transcript styling.

## What was built

```
paper_agent/api/server.py     # +GET/HEAD /app → paper_agent/webapp/index.html + StaticFiles mount at /app
                              # +POST /api/capture + GET /api/capture/{id} — in-memory capture mailbox
                              #   (cap 20, TTL 120 s, sweep-on-access; NOT a source of truth — vault is)
                              # +GET /api/sse-probe — dev-only dummy SSE endpoint (10 tokens, 300 ms apart)
                              # ASK log line now includes fresh= (body-field verification)
paper_agent/webapp/           # NEW — the environment-agnostic page (browser tab / PWA / panel WKWebView):
  index.html                  # quote, composer (Enter=send, ⇧Enter=newline), continue/fresh toggle with
                              #   live resolve preview, streaming transcript, paper override picker,
                              #   daemon-down banner with 5 s recovery polling; <base href="/app/"> fixes
                              #   relative assets at the slashless /app URL
  styles.css                  # Spotlight-style, dark-first, translucent (composites over NSVisualEffectView);
                              #   global [hidden]{display:none !important} guard (bug fix — see Key decisions)
  app.js                      # state model per §5.4; #capture=<id> hydration (+hashchange); SSE ask flow
                              #   (cross-space retarget, ingest banners, saved-to-vault footer, copy button,
                              #   error states); page-state logging (INIT/RESOLVE-OK/MARK-DAEMON-DOWN/RECOVERED)
  sse.js                      # ask.tsx SSE parser port — chunk-split, \r\n normalization, multi data-line
                              #   join, [ERROR]-gated error detail; DOM-free, unit-tested with bun (12/12)
  marked.min.js               # vendored markdown renderer + DOM sanitizer (script/on* strip)
  manifest.json, sw.js, icon.svg   # optional PWA (network-first shell so dev iterations never go stale; API never cached)
  probe.html                  # §6.5 WKWebView streaming-probe page (inter-token timing verdict)
paper-agent-swift-app/PaperAgent/
  PaperAgent.xcodeproj        # handwritten pbxproj; ad-hoc signed, LSUIElement (no Dock icon),
                              #   NSAppTransportSecurity → NSAllowsLocalNetworking
  build.sh                    # builds PaperAgent.app via CLT swiftc — NO Xcode license needed; the xcodeproj
                              #   remains for the Xcode GUI path (needs sudo xcodebuild -license + xcode-select)
  PaperAgent/
    PaperAgentApp.swift       # @main SwiftUI; MenuBarExtra (Open Panel / New Thread / conditional
                              #   "Grant Accessibility…" + "Allow … Automation…" / daemon status / Quit);
                              #   icon = filled circle (daemon up) / outline (down)
    AppCore.swift             # wiring; daemonUrl from UserDefaults; capture→handoff→show pipeline — capture
                              #   runs BEFORE orderFrontRegardless (Chrome PDF selection survives focus loss);
                              #   daemon-down → panel still shows (page renders its own recovery state);
                              #   lifetime ProcessInfo beginActivity assertion (anti-App-Nap — do not remove)
    PanelController.swift     # persistent NSPanel + persistent WKWebView (D5: transcript survives hide/show;
                              #   hide = orderOut only, never destroy); vibrancy .hudWindow behind transparent
                              #   web view; 560×640, top-center of the mouse's screen (15 % margin, repositioned
                              #   every show); nonPersistent data store (never serves a stale cached page);
                              #   page console piping to stdout; Escape local monitor + click-outside global
                              #   monitor + resignKey → orderOut
    Panel.swift               # KeyablePanel — borderless + nonactivating, canBecomeKey (WKWebView typing)
    HealthCheck.swift         # GET /api/health every 15 s (drives the menu icon); blocking isUp() for the
                              #   hotkey path (down → skip capture, show panel immediately)
    HotkeyCenter.swift        # Carbon RegisterEventHotKey, ⌘⌃⇧A (kVK_ANSI_A, cmd|ctrl|shift) via
                              #   GetApplicationEventTarget; registration result checked + logged (§7.2);
                              #   toggle semantics: hide if shown+key, else capture→show
    CaptureService.swift      # capture.ts ladder port: frontmost app → AX kAXSelectedTextAttribute (silent
                              #   fail → next) → Chrome/Safari URL+title AppleScript (verbatim, battle-tested
                              #   scripts) → browser JS selection → clipboard fallback (⌘C via System Events to
                              #   the browser process WITHOUT activating it; Chrome 0.3 s + 0.5 s retry, Safari
                              #   single attempt); errAEEventNotPermitted (-1743) → surfaced as menu hint
    HandoffService.swift      # POST /api/capture → {id} → panel loads /app#capture=<id> (full reload per plan)
  probe/probe.swift           # §6.5 streaming probe app (verdict via WKScriptMessage)
  probe/probe2.swift          # capture-flow probe: loads the real page with console piping + banner visibility check
```

## Key decisions

- **WKWebView SSE streaming verified working (§6.5 risk gate resolved — no bridge needed).** Probe measured fetch + ReadableStream delivering tokens at ~300 ms gaps matching server pacing exactly. Two probe gotchas recorded in the migration plan: WKWebView caches aggressively (cache-bust probe URLs with a query param) and the daemon sends `\r\n\r\n` event separators (normalize before splitting on `\n\n` — `sse.js` does).
- **Capture handoff via the `/api/capture` mailbox (D4)** — not `evaluateJavaScript` injection — so the page stays browser-tab/PWA-testable and was built and verified entirely in Chrome before any Swift existed (the plan's layering rule).
- **App Nap was real and silent:** an LSUIElement app whose panel is ordered out gets napped — timers/network suspend, page fetches fail and get misread as "daemon not reachable", and recovery polls fire in coalesced bursts. Fixed with a lifetime `ProcessInfo.beginActivity(.userInitiatedAllowingIdleSystemSleep)` assertion. Verified: health polls resumed exact 15 s cadence.
- **The persistent "Daemon not reachable" banner was a CSS bug, not a daemon problem:** `#daemon-banner`'s `display: flex` overrode the HTML `hidden` attribute's UA `display: none` (author CSS wins), so the banner rendered unconditionally on every page load while the daemon was healthy and no errors ever logged. Fixed with the global `[hidden] { display: none !important }` guard; verified programmatically (probe2 reads computed visibility).
- **Error attribution discipline:** `renderAll()` originally sat inside `refreshResolve`'s try/catch — any DOM throw would have been misreported as "daemon down". Rendering now happens outside network try/catch; the daemon-down banner carries the actual error reason in parentheses.
- **Instrumentation built in:** page `console.*` + uncaught errors pipe to the app's stdout; stdout unbuffered (`setvbuf`) so terminal-redirected logs are live; the page logs every state transition. App log: `/tmp/paperagent-app.log` when launched from a terminal; daemon log: whatever `serve` was redirected to.
- **Hotkey ⌘⌃⇧A is the user-chosen throwaway** (Raycast owns ⌘⇧P until cutover); Carbon registration failures are logged because collisions fail silently on macOS.
- **Swift builds via `build.sh` + CommandLineTools `swiftc`** — sidesteps the Xcode license entirely; `DEVELOPER_DIR=…` prefixes any `xcodebuild` use until `sudo xcode-select -s /Applications/Xcode.app` is run.

## Verified

```
# Phase 1 (§4.4): /api/health ok · /app 200 text/html · POST/GET /api/capture round-trip ·
#   404 on unknown/expired · TTL sweep + 20-cap in-process tests · compileall clean
# Phase 2 (§5.6): 12/12 SSE parser bun tests (chunk splits, \r\n, multi data-line, sentinel gating,
#   keepalives) · real end-to-end ask stream parsed (resolved→thread→tokens→[DONE]→session_path) ·
#   all resolve states (continuing/fresh/new_paper/no_paper) · all assets 200
# Phase 3 (§6.5): probe STREAMING-OK — 10 tokens, gaps [263,302,301,301,…]
# Phase 4: banner computed visibility = none with daemon healthy · App Nap defeated (2 polls/32 s) ·
#   page console pipe + state logging live
# LIVE user test (Safari): CAPTURE app=Safari url=arxiv.org/pdf/2601.18795 selected=0 → resolve said
#   fresh/new_paper (correct — no Eagle pollution) → ask auto-downloaded + ingested "Reuse your FLOPs"
#   into the vault → only failure was the expired OpenRouter key (401, page showed it inline)
```

## Immediate next steps (agreed order)

1. **`.env` — expired OpenRouter key (user action; agents never touch `.env`):** create a new key at openrouter.ai/settings/keys, replace `OPENROUTER_API_KEY`, restart the daemon from the repo root. The "Reuse your FLOPs" paper is already ingested, so the next ask on it will be instant.
2. **Safari selection capture:** enable Safari → Settings → Advanced → *Show features for web developers* → Develop menu → **Allow JavaScript from Apple Events** (or approve the System Events TCC prompt for the ⌘C fallback). Until then: URL capture works (right paper, right thread state) but no quoted selection and section-matching falls back to the same-paper continue rule.
3. **Zen support decision:** Zen (user's daily browser, Firefox-based) has **no tab AppleScript** — URL capture is impossible via the script ladder; probes confirmed only `count windows` + window name work (name contains the paper title and, for arXiv PDFs, the arXiv ID). Options: (a) extend the ladder with a window-title → arXiv-ID → abs-URL heuristic + generalized clipboard fallback (⌘C to any frontmost process), or (b) keep Safari/Chrome for paper reading. Decide after a day of dogfooding.
4. **Swift Phase 5 polish (trimmable, by feel):** window grows with transcript content; clipboard save/restore around the ⌘C fallback (it currently clobbers the clipboard — known, accepted until now); launch-at-login (SMAppService); app icon; settings surface (hotkey configurability, daemonUrl UI); long-quote clamp polish (basic CSS clamp already in).
5. **Swift Phase 6 cutover:** remove Raycast's ⌘⇧P binding → Swift app takes **⌘⇧P**; launch-at-login ON; one week of zero-Raycast dogfood (rollback = rebind Raycast, instant; extension code stays in-repo); update `AGENTS.md` + `outputs.md` architecture notes (this section partially does that already).
6. **Then 9.1 prompt tuning** (design notes in phase-plan.md) **and 9.6 space control plane** — its design notes target Raycast (`spaces.tsx` + `POST /api/spaces`, still unbuilt) and need a web-page redesign instead.
7. **Then Phases 10–14** (multimodal — via the 9.7 OpenRouter transport as an optional `LLMClient` capability, NOT the deleted Gemini Vision path; MCP adapter; WhatsApp bridge; iPad; voice). Phase 8 (search) stays deferred.

---

# Phase 9.5 Results — Summary + Synthesis Polish

## What was built

```
paper_agent/
  llm/
    base.py               # +reasoning_effort param → OpenRouter extra_body
                          #   {"reasoning": {"enabled": true, "effort": ...}} on every
                          #   completions call (generate + generate_structured, both branches)
                          #   +aclose() — explicit client close
                          #   +install_asyncgen_teardown_filter() — loop exception handler
                          #   that downgrades the root-caused httpcore2 asyncgen finalization
                          #   noise (see Key decisions); auto-installed by LLMClient.__init__
    __init__.py           # +get_structured_client() factory; shared _build_client()
    prompts.py            # SYNTHESIS_SCHEMA / build_synthesize_prompt REPLACED by
                          #   SYNTHESIS_VERDICTS_SCHEMA + build_synthesize_pairwise_prompt()
                          #   (forced per-pair verdicts, "unrelated" is an explicit value) +
                          #   OVERALL_SYNTHESIS_SCHEMA + build_overall_synthesis_prompt()
  config.py               # +get_structured_llm_settings() — structured_model /
                          #   structured_provider / structured_reasoning_effort config.yaml
                          #   keys (all fall back to main model / reasoning_effort);
                          #   get_llm_settings() also returns reasoning_effort;
                          #   DEFAULT_MODEL = openai/gpt-5.6-luna
  agent/
    synthesize.py         # REWRITE: one-vs-rest — paper i vs papers i+1..N in ONE call each
                          #   (every pair judged exactly once, N-1 calls). Forced verdict per
                          #   other paper: {other_paper, related, relationship, insight};
                          #   emptiness impossible by construction. Matched by title; missing
                          #   verdict → 1 retry → PaperAgentError. overall_synthesis from a
                          #   final call over confirmed connections (short-circuits to an
                          #   honest canned string when 0 connections). synthesis.json:
                          #   {connections, unrelated, overall_synthesis}. cross-paper-insights.md
                          #   gains a "Judged Unrelated" section. Uses structured client.
    summarize.py          # +summary.json sidecar {summary, summarized_qa_count, summarized_at,
                          #   model}; metadata.yaml purely descriptive again (legacy `summary`
                          #   key popped on re-summarize). Uses structured client.
    knowledge.py          # summaries read via vault.get_paper_summary() (sidecar + legacy
                          #   fallback); structured client for both update_knowledge() and
                          #   update_open_questions()
    ask.py                # closes the LLM client after streaming (finally: aclose());
                          #   session/writer.py _generate_slug closes its client too
  vault.py                # +get_paper_summary() — summary.json sidecar, falls back to legacy
                          #   metadata.yaml `summary` (freshness None); +is_summary_stale() →
                          #   bool | None; regenerate_index marks stale summaries "⚠ stale"
  api/server.py           # papers list + has_summary / summary_stale / qa_count /
                          #   summarized_qa_count; the 4 knowledge endpoints' key-check uses
                          #   structured settings
  cli.py                  # status: "structured model: … (reasoning: …)" when configured
~/.paper-vault/.paper-agent/config.yaml
                          # model: openai/gpt-5.6-luna, reasoning_effort: low — ONE model
                          # for everything (structured_* keys supported but unused)
```

## Key decisions

- **No temperature=0 (9.5.1, revised):** determinism comes from forced-verdict schemas + a reasoning model, not sampling knobs. Structured calls (summarize/synthesize/knowledge/open-questions) route to a dedicated structured client configured via config.yaml, falling back to the main model. After verification the split was collapsed: **everything (streaming ask included) runs `openai/gpt-5.6-luna` at `reasoning: low`** — vault config is just `model` + `reasoning_effort`, and `DEFAULT_MODEL` is luna. The `structured_*` keys remain supported for a future split.
- **One-vs-rest forced verdicts, not retry-union (9.5.2, redesigned):** the old open-ended "find connections; empty array is valid" prompt let the model lazily bail. Retry+union was rejected as a band-aid (deterministic sampling makes retries pointless; it can't distinguish a real negative from a bail). Instead each paper runs against all remaining papers in ONE call and the schema forces a verdict for EVERY other paper — `related: bool` + relationship (`unrelated` is an explicit enum value) + insight. Every pair judged exactly once; "no connections" is now a verified negative, rendered under "Judged Unrelated". One retry remains only for malformed JSON.
- **Freshness lives with the summary (9.5.3):** `summary.json` records `summarized_qa_count` + `summarized_at` + model. Staleness (current `get_qa_by_paper()` count ≠ summarized count) surfaces as `summary_stale` in the papers API, "⚠ stale" in `index.md`, and `is_summary_stale()` for future consumers. Legacy summaries report None (unknown), not false-stale.
- **Sidecar .json everywhere (9.5.4):** `papers/{slug}/summary.json` + `summaries/synthesis.json` are THE structured storage; `metadata.yaml` is purely descriptive. Readers fall back to the legacy metadata.yaml `summary` key so pre-9.5.4 vaults keep working; re-summarizing migrates automatically.
- **API contract unchanged:** synthesize still returns `{status, connections, markdown}` (0 connections now = `ok`, not `skipped`); Raycast needed no changes.
- **9.5.5 (summary-previous.md) skipped** — regenerable artifact, low value.
- **Asyncgen teardown noise — root-caused and filtered.** Streaming asks printed `RuntimeError: generator didn't stop after athrow()` tracebacks at generator finalization. Minimal repro + live-generator inventory showed openai 3.8's SSE loop `break`s on `[DONE]` without exhausting httpcore2's response-body generator chain — ~10 orphaned suspended generators (openai → httpx2 → httpcore2). GC later athrows GeneratorExit into them and httpcore2's `except BaseException: await self.aclose(); raise exc` pattern fails the asyncgen close protocol. **No leak** — openai's `finally: await response.aclose()` already released the connection; the daemon accumulates nothing per request. `LLMClient.__init__` installs a loop exception handler matching exactly this RuntimeError and logging it at debug; everything else delegates to the previous/default handler. Upstream-worthy; revisit when openai/httpcore2 fix the interaction.

## Verified

```
paper-agent status
# → provider: openai · model: openai/gpt-5.6-luna (reasoning: low)

# Fresh vault: init research → ingest attention + eagle → 6 seeded Q&A each
paper-agent summarize (both papers)
# → summary.json {summarized_qa_count: 6, model: openai/gpt-5.6-luna}; metadata.yaml clean

paper-agent synthesize --space research    (×2 CLI + ×1 API)
# → 1 connection every run, same pair (Attention ↔ Eagle), no empty bail-outs
# → relationship label varies (builds_on vs shares_method) — verdict stable, wording not

# Streaming ask on luna (CLI + daemon SSE) — the unified-model change
paper-agent ask "what budget does it target?" --space research
# → streamed markdown answer grounded in the active paper, saved, exit 0, stderr clean
#   (the httpcore2 asyncgen teardown noise is root-caused + filtered — see Key decisions)
# selection-only ask → AI slug path works (minimax-bayes-rule-20260904.md)

# Staleness loop
# + 1 Q&A on attention → is_summary_stale True · index.md "⚠ stale" · papers API stale=True (7 vs 6)
# POST summarize via API → papers API stale=False (7 vs 7)

POST /knowledge → ok (5 themes, 9 facts) · POST /open-questions → ok (9 questions)

# Legacy fallback (scratch vault, metadata.yaml-embedded summary)
# get_paper_summary reads it; is_summary_stale → None (unknown)

python3 -m compileall paper_agent   ✓
```

## Notes for next phase

- Remaining Phase 9: 9.1 prompt tuning, 9.6 space control plane (`spaces.tsx` + `POST /api/spaces`)
- The research vault was rebuilt fresh for this verification (the old one no longer existed): 2 papers, seeded Q&A, real summaries + synthesis — a usable starting state
- Raycast `end-paper.tsx` papers list could surface `summary_stale` in a future pass (fields are already in the API)
- Daemon restart still required after this rewrite (`lsof -nP -iTCP:8765`)

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

## Notes for next phase (remaining Phase 9)

- Phase 9.5 (Summary + Synthesis Polish) is DONE — see the Phase 9.5 Results section above.
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
