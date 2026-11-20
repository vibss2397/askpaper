# Migration Plan — Raycast → Swift Panel App

**Status:** Planning (no code written yet)
**Owner:** paper-agent project
**Audience:** A new AI coding session (or future you) picking this up cold. This document is the
single source of truth for the migration. Read it top to bottom before writing any code.

---

## 1. What this migration is

Replace the Raycast extension as the user-facing UI with a native macOS Swift panel app
(Spotlight-style floating window) that hosts a small web page. The daemon (`paper-agent serve`,
Python/FastAPI) is untouched in architecture — it gains two small additions (static file serving
and a capture-store endpoint). Raycast is deleted from the daily loop at the end; nothing
replaces it except the Swift app itself.

### Why (design goals settled in discussion)

1. Raycast's UI chrome cannot be made minimal/modern: fixed half-screen window, no opacity
   control, no bottom-anchored composer, no single-page chat. These are hard platform limits.
2. Target look: a Spotlight-like overlay — small (~560 px wide), top-centered, vibrancy blur,
   ~0.8 opacity, one page containing: quoted selection, question composer, continue/fresh
   toggle, scrollable markdown transcript with live SSE streaming.
3. Raycast's remaining jobs (global hotkey, OS-level selection capture, handoff to daemon) are
   all standard macOS machinery a Swift app can own natively.

### Target architecture

```
Cmd+Shift+P (any app)
   → PaperAgent.app (menu-bar agent, always running)
       1. AppleScript capture: selection + frontmost app + browser URL/title
       2. POST /api/capture → {id}                (daemon, localhost:8765)
       3. orderFront panel, load /app#capture=<id> (WKWebView, one persistent instance)
   → Web page (single index.html served by the daemon)
       - fetches capture by id → shows quote in composer
       - POST /api/resolve → thread-state preview (● continue / ○ fresh)
       - POST /api/spaces/{name}/ask → SSE stream → markdown transcript
   → Daemon (paper_agent/, FastAPI) — UNCHANGED core, +2 small endpoints
   → ~/.paper-vault/ — unchanged
```

Layering rule (build order follows this):

```
Layer 1: daemon additions      (Python, ~60 lines total)
Layer 2: web page              (one index.html, vanilla JS, no build step, no framework)
Layer 3: Swift shell           (Xcode project; window + hotkey + capture only)
```

The web page is environment-agnostic: it works in a plain browser tab, as an installed PWA,
and inside the Swift panel's WKWebView — same file, same behavior. Build and verify it in a
browser BEFORE any Swift exists.

---

## 2. Current state (what exists today — do not re-derive)

### Repo layout

- `paper_agent/` — Python package (daemon, ingestion, llm, agent, session, vault, api)
- `raycast-extensions/paper-agent/` — TypeScript/React Raycast extension (the thing being replaced)
- `~/.paper-vault/` — vault: `spaces/{name}/papers|sessions|summaries`, `knowledge.md`,
  `open-questions.md`, `index.md`, `.paper-agent/config.yaml`
- `.env` — **NEVER read, print, or log** (repo rule from AGENTS.md). Contains
  `OPENROUTER_API_KEY` and `PAPER_AGENT_SECRET`. Reference `.env.example` for names only.

### Daemon (keep as-is)

- Started with `uv run paper-agent serve --port 8765` from the **project root** (it discovers
  `.env` via cwd — starting elsewhere breaks the API key; known operational gotcha).
- Stale-daemon gotcha: a daemon from days ago can still hold port 8765. When behavior seems
  stale: `lsof -nP -iTCP:8765`, kill, restart from project root.
- Config: `~/.paper-vault/.paper-agent/config.yaml` → `model: openai/gpt-5.6-luna`,
  `reasoning_effort: low`, optional `provider`, `base_url`, `structured_*` keys. All LLM calls
  go through OpenRouter via the OpenAI-compatible transport in `paper_agent/llm/base.py`.

### Existing API contract (the page consumes these — all already built)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | `{status, version}` — health polling |
| GET | `/api/spaces` | `[{name, sessions}]` |
| GET | `/api/context` | `{last_space, last_source_*, active_paper_id, last_session_file}` |
| GET/PUT | `/api/context` | partial merge update |
| POST | `/api/resolve` | Thread-state preview — see §5.2 |
| POST | `/api/spaces/{name}/ask` | SSE stream — see §5.3 |
| GET | `/api/spaces/{name}/papers` | `[{paper_id, title, type, source_url, ingested_at, page_count, conversion_method, has_summary, summary_stale, qa_count, summarized_qa_count}]` |
| GET | `/api/spaces/{name}/sessions` | session list |
| GET | `/api/spaces/{name}/sessions/{date}` | parsed Q&A |
| GET | `/api/spaces/{name}/session-files/{filename}` | reading-session files (path-traversal-guarded) |
| POST | `/api/spaces/{name}/papers` | ingest by `{url}` or multipart file |
| POST | `/api/spaces/{name}/summarize` / `synthesize` / `knowledge` / `open-questions` | knowledge loop |
| DELETE | `/api/spaces/{name}/contents`, `/api/spaces/{name}` | destructive; require `X-Paper-Agent-Secret` header |

CORS: regex allows `http://localhost:*` / `127.0.0.1:*` only. The page is served BY the daemon
(same origin) so CORS is a non-issue in the primary deployment.

### Raycast behavior that must be replicated (source: `raycast-extensions/paper-agent/src/`)

**Capture pipeline** (`capture.ts`) — priority order matters:

1. Selection: Raycast's proprietary `getSelectedText()`. **No direct Swift equivalent** — the
   Swift app replaces this step with Accessibility API `AXUIElement` (focused element,
   `kAXSelectedTextAttribute`), falling through to browser JS selection and clipboard (below).
2. Frontmost app name.
3. If Chrome (or no selection and not Safari):
   - AppleScript: URL + title of active tab of front window.
   - AppleScript: `execute front window's active tab javascript "window.getSelection().toString()"`.
   - Clipboard fallback (for Chrome PDF viewer where JS selection fails): clear clipboard,
     `tell System Events → keystroke "c" using command down` targeted at Chrome's process
     **without activating it** (Chrome's PDF viewer loses selection on focus loss), delay 0.3 s,
     read clipboard; retry once with delay 0.5 s.
4. If Safari (or no selection and not Chrome): same ladder — URL/title AppleScript, JS selection
   (`do JavaScript "window.getSelection().toString()" in front document`), clipboard fallback.

**Ask flow** (`ask.tsx`) — the semantics the page must preserve:

- On load: hydrate from captured URL via `POST /api/resolve` → switch space to the owning space
  ("space follows paper"), seed transcript from `recent_qa`, show thread-state preview.
- Space is NEVER user-chosen in the UI (settled design decision). It comes from resolve /
  daemon context. The space dropdown is dead.
- Paper resolution: server-side from URL. Explicit override only via a picker (for URL-less
  contexts like PDFs in Preview) — keep as a small in-page picker fed by
  `GET /api/spaces/{name}/papers`.
- Continue vs fresh: derived from `_should_continue` (section matching) but previewable via
  `/api/resolve`; user-facing control is a single toggle (checkbox) that maps to the `fresh`
  field in the ask body. The toggle's LABEL carries the live preview (e.g. "Continue thread ·
  §3.3 · 4 Q&A" / "Fresh thread · new paper will be ingested").
- No URL + no selection → daemon falls back to last active paper (global rule) — the page just
  sends what it has; the server decides.
- SSE events handled: `resolved`, `thread`, `ingesting`, `ingested`, `ingest_failed`,
  `session_path`, `[DONE]`, raw tokens. See §5.3.
- Saved-to-vault confirmation surfaced after stream end.

---

## 3. Key design decisions (settled — do not relitigate without the user)

| # | Decision |
|---|---|
| D1 | Swift shell + WKWebView hosting the web page (not pure SwiftUI, not Tauri, not Electron). Swift surface stays tiny: window, hotkey, capture, handoff. |
| D2 | Web page: single static `index.html`, vanilla HTML/CSS/JS, served by the daemon at `/app`. No framework, no build step, no node toolchain. SSE via `fetch` + `ReadableStream`. |
| D3 | Minimal UI (settled): quote (selected text) + question composer + continue/fresh toggle + streaming transcript. No space picker, no paper line (except override picker), no history panel — full history lives in the vault / Obsidian / `session-history` command (kept until Phase 6+). |
| D4 | Handoff mechanism: `POST /api/capture` on the daemon stores the capture, page loads `/app#capture=<id>` and fetches it. (Alternative B — `evaluateJavaScript` injection — rejected as primary because it makes the page panel-only; the capture endpoint keeps the page browser-testable and PWA-compatible.) |
| D5 | Window: NSPanel, nonactivating, floating, frameless, vibrancy (NSVisualEffectView, `.hudWindow` or `.sidebar` material), ~560 px wide, top-centered on the screen with the mouse/key window. Panel instance and WKWebView persist across toggles so the transcript survives hide/show. |
| D6 | Global hotkey via Carbon `RegisterEventHotKey` (what Spotlight-era apps use; reliable, no event tap needed). |
| D7 | Raycast stays installed and working during the entire migration (parallel operation is safe — both are just daemon clients). Cutover (Phase 6) = unbind Raycast hotkey, bind Swift hotkey. |
| D8 | The daemon itself is NOT auto-started by the Swift app in this migration (out of scope; see §9 "daemon LaunchAgent" as a follow-up). The Swift app must degrade gracefully when the daemon is down. |

---

## 4. Layer 1 — daemon changes (Python, small and isolated)

All changes in `paper_agent/api/server.py` (+ static assets directory). No changes to agent,
ingestion, llm, session, or vault code.

### 4.1 Static serving

- Mount a static directory at `/app` (FastAPI `StaticFiles` or explicit routes). Serves
  `paper_agent/webapp/` (or `webapp/` at repo root — pick `paper_agent/webapp/` so it ships
  with the package) containing `index.html` (+ optional `app.js`, `styles.css`, `manifest.json`,
  `sw.js` — see §6.4 for PWA note).
- `GET /app` (and `/app/`) → `index.html`. No auth (localhost-only tool, consistent with the
  rest of the API).

### 4.2 Capture store

- `POST /api/capture` — body `{selected_text, source_app, source_title, source_url}` →
  `{id, expires_at}`. In-memory dict on the app state, id = uuid4 hex (short form fine).
  Single-user tool: no auth, no persistence, cap the dict (e.g. keep last 20), TTL 120 s
  (sweep on access).
- `GET /api/capture/{id}` → the payload + `age` (or 404 if expired/unknown).
- Purpose: decouple "Swift captured something" from "page is loaded and ready". Also gives the
  browser/PWA path a future entry point.
- **Do NOT make this the source of truth for anything** — it is a message mailbox, not state.
  The vault remains the conversation state (existing 9.5 decision).

### 4.3 Non-goals

- No new auth, no sessions, no websocket, no changes to SSE format, no changes to ask/resolve
  semantics. If a change feels needed in `paper_agent/agent` or `session` to make the page
  work, stop and re-read §2 — the endpoints already support everything the Raycast UI did.

### 4.4 Verification (Phase 1 exit criteria)

```
uv run paper-agent serve --port 8765          # from project root
curl localhost:8765/api/health                → ok
curl -I localhost:8765/app                    → 200, text/html
curl -X POST localhost:8765/api/capture -H 'Content-Type: application/json' \
     -d '{"selected_text":"x","source_app":"Chrome","source_title":"t","source_url":"u"}'
                                              → {"id":"...","expires_at":...}
curl localhost:8765/api/capture/<id>          → payload
# (wait > TTL) curl again                     → 404
python3 -m compileall paper_agent             → clean
```

---

## 5. Layer 2 — the web page (`index.html`)

### 5.1 Layout (the settled minimal design)

One page, two visual zones:

```
┌──────────────────────────────────────────────┐
│ ❝ "Multi-head attention allows the model…"   │  ← quoted selection (hidden when none)
│ ┌──────────────────────────────────────────┐ │
│ │ Ask a follow-up…                    ⏎    │ │  ← composer (textarea, autofocus)
│ └──────────────────────────────────────────┘ │
│ ☑ Continue thread · §3.3 · 4 Q&A            │  ← toggle (label = live resolve preview)
├──────────────────────────────────────────────┤
│ You: why scale by √dk?                       │  ← transcript, scrollable,
│ ● The √dk scaling counteracts…█              │     newest at bottom, markdown rendered,
│ You: what do FF networks do?                 │     auto-scroll while streaming,
│ ● Two linear transforms with ReLU…           │     stop auto-scroll if user scrolls up
└──────────────────────────────────────────────┘
```

- Paper title + space: shown only as a small header line above the transcript
  (from `resolved` SSE event / resolve response) — not a form control.
- Continue/fresh: checkbox or segmented control. Label variants:
  - `☑ Continue thread · §3.3 · 4 Q&A` (resolve says continuing)
  - `☑ Continue thread · §3.5 · 4 Q&A` (resolve says fresh — different section; honest label:
    show `○ Fresh thread · §3.5` instead, follow resolve's `thread_state`, don't fake it)
  - `○ Fresh thread · new paper` (unknown URL → will auto-ingest on ask)
  - `○ Fresh thread · no paper` (selection-only answer)
- Ingestion status (`ingesting` event) → thin status line ("Downloading paper…") above the
  streaming answer; cleared on `ingested`; failure shown inline with the fallback note.
- After stream end: subtle "Saved to vault · <file>" footer on the turn.
- Markdown rendering: a tiny renderer in-page. Constraint of "no build step / no framework"
  allows a vendored single-file library (e.g. marked.min.js saved next to index.html —
  vendoring a file is not a build step). Sanitize or trust-at-your-own-risk: source is the
  user's own daemon + their own LLM; a basic strip of `<script>` is still recommended.
- Actions per turn: copy answer (button on hover). Keep it minimal — no chrome.

### 5.2 Thread-state preview (`POST /api/resolve`)

Body: `{source_url, selected_text, space?}` (space optional — omit; daemon resolves) →

```json
{
  "found": true,
  "space": "research",
  "paper_id": "attention-is-all-you-need",
  "title": "Attention Is All You Need",
  "qa_count": 4,
  "recent_qa": [{"id","question","answer","section"}],
  "thread_state": "continuing | fresh | new_paper | no_paper",
  "section": "3.3 Position-wise Feed-Forward Networks"
}
```

The page calls resolve: on load (with capture in hand), after `⌘R`-equivalent refresh, and
whenever the toggle is manually flipped back to "continue" (re-preview). The preview is
advisory — the server re-decides on ask; the label can never lie because it mirrors the same
logic (existing design guarantee, keep it).

### 5.3 Ask + SSE (`POST /api/spaces/{name}/ask`)

Body (all fields the Raycast UI sends today):

```json
{
  "question": "…",
  "selected_text": "…",
  "source_app": "Google Chrome",
  "source_title": "…",
  "source_url": "https://arxiv.org/abs/1706.03762",
  "fresh": false,
  "paper_id": "optional-explicit-override"
}
```

SSE grammar (existing — parse exactly like `ask.tsx` does):

- `data: <token>` lines — append to current answer. Multiple `data:` lines per event are
  joined with `\n` (the parser in ask.tsx handles this; port it).
- `data: {"status": "resolved", "space": "…", "paper": {"paper_id","title"}}` — update the
  header line; if `space` differs from the one used in the URL path, subsequent asks must
  target the new space (cross-space retarget; store the active space from this event).
- `data: {"status": "thread", "section": "…", "continued": bool}`
- `data: {"status": "ingesting", "message": "…"}` / `"ingested"` /
  `{"status": "ingest_failed", "error": "…"}`
- `data: [DONE]` — stream sentinel.
- `data: {"session_path": "…"}` — save confirmation.
- `data: [ERROR]` — error sentinel.
- Non-2xx response: JSON `{detail}` → render inline error + "Is the daemon running?"
  hint (ask.tsx behavior).

Newlines within tokens: events are separated by `\n\n`; normalize `\r\n` → `\n` (ask.tsx does).

### 5.4 Page state model

- `capture` {selected_text, source_*} — from `#capture=<id>` fetch, or empty.
- `resolve` — last resolve response (drives toggle label + header).
- `turns` [{question, answer}] — the visible transcript. Seeded from `resolve.recent_qa`
  (cap at last 10, same as today); grows as asks complete. NOT durable — closing the page
  clears it (the vault is the truth; reopening re-seeds from resolve). 
- `streaming` {question, partial, banner} — the in-flight turn.
- `freshOverride` — the toggle. Default: unchecked (continue), unless resolve says fresh.
- Composer: Enter = send, Shift+Enter = newline. While streaming: composer disabled (or
  queued — disabled is simpler and matches current behavior).

### 5.5 PWA note (optional, cheap, do in Phase 2)

Manifest + minimal service worker (cache-first for the shell, network-only for API) makes the
page installable as a standalone window — a useful intermediate artifact and a fallback UI if
the Swift panel ever breaks. ~20 lines. Not required for the Swift path; skip if time-boxed.

### 5.6 Verification (Phase 2 exit criteria — entirely in Chrome, no Swift)

```
uv run paper-agent serve --port 8765
open http://localhost:8765/app
# 1. bare load (no capture): composer + toggle "no paper" or active-paper preview
# 2. simulate capture: curl POST /api/capture with an arXiv URL + a real selection snippet,
#    then open /app#capture=<id> → quote appears, toggle shows real thread state
# 3. ask a question → tokens stream, markdown renders, saved-to-vault footer
# 4. follow-up same section → toggle label says continue, answer uses history
# 5. flip to fresh → body includes "fresh": true (verify in daemon logs)
# 6. unknown URL capture → ingesting banner → answer grounded in newly ingested paper
# 7. kill daemon → page shows daemon-down error, not a blank screen; restart → recovers
# 8. paper override picker lists papers of the resolved space
```

---

## 6. Layer 3 — the Swift app

### 6.1 Project shape

- New Xcode project **inside this repo** at `paper-agent-swift-app/PaperAgent/`
  (source lives here; this migration_plan.md stays at the package root).
- Template: macOS App, SwiftUI lifecycle, **no** storyboard — but the panel itself is AppKit
  (`NSPanel`); SwiftUI `MenuBarExtra` for the menu-bar presence. Mixing is fine and normal.
- Bundle id: `com.vibhu.paperagent` (or local equivalent). Signing: **ad-hoc / "Sign to Run
  Locally"** — this app is never distributed, no Apple Developer account, no notarization.
- Target macOS: whatever the machine runs (14+/15 fine). Tooling prerequisite: Xcode installed.
- One persistent panel + one persistent WKWebView for the app's lifetime (D5). Never destroy
  on dismiss — hide only. This is what makes hide/show feel instant and keeps the transcript.

### 6.2 Components

```
AppDelegate / AppCore
├── StatusItem (MenuBarExtra): icon (● green = daemon healthy / ◻ gray = down / red = error)
│     menu: Open Panel, New Thread (reload /app), daemon status line, Quit
├── HotkeyCenter        — Carbon RegisterEventHotKey, default Cmd+Shift+P (config in UserDefaults)
├── CaptureService      — runs the capture ladder (§6.3) BEFORE showing the panel
├── HandoffService      — POST /api/capture → {id} → panel.load("/app#capture=<id>")
├── PanelController     — NSPanel lifecycle, sizing, positioning, show/hide
└── HealthCheck         — GET /api/health every 15 s, drives menu-bar icon + panel banner
```

### 6.3 Capture ladder (port of capture.ts — ORDER MATTERS)

Run capture **before** `panel.orderFrontRegardless()` — focusing the panel can destroy the
selection in the source app (Chrome PDF viewer specifically).

1. Frontmost app: `NSWorkspace.shared.frontmostApplication` (name, bundle id).
2. AX selection (replaces Raycast's proprietary `getSelectedText`): `AXUIElementCopyElementAttributeValue`
   on the system-wide focused element for `kAXSelectedTextAttribute`. Requires **Accessibility
   permission** (see §7.1). Fails silently → next step.
3. Browser URL/title AppleScript (Chrome or Safari, same scripts as capture.ts — keep them
   verbatim, they are battle-tested):
   - Chrome: `tell application "Google Chrome" to get URL/title of active tab of front window`
   - Safari: `tell application "Safari" to get URL/name of current tab of front window`
4. Browser JS selection: `execute ... javascript "window.getSelection().toString()"` (Chrome) /
   `do JavaScript ... in front document` (Safari).
5. Clipboard fallback (PDF viewer case): clear pasteboard → System Events keystroke "c" with
   command down targeted at the browser process **without activating it** → delay 0.3 s →
   read pasteboard → retry once at 0.5 s.
6. Compose the capture: `{selected_text, source_app, source_title, source_url}` — always POST
   it to `/api/capture` (even when empty: an empty capture still means "hotkey pressed, no
   selection" and the page handles that case — active-paper fallback).

Run AppleScript via `NSAppleScript` in-process (add the `com.apple.security.scripting-targets`
/ Apple Events handling as TCC prompts appear — see §7.1). Note: a plain (non-sandboxed)
ad-hoc app does not need entitlements for AppleScript; macOS will show TCC prompts per target
app on first use.

### 6.4 Panel details (the polish that makes it "Spotlight")

- `NSPanel` style: `borderless` + `nonactivatingPanel`. It must be able to become key window
  (needed for WKWebView keyboard input) — override `canBecomeKey` true. Nonactivating means
  the source app keeps focus visually; that is fine because capture already happened.
- Content: `NSVisualEffectView` (material `.hudWindow` or `.sidebar`, blending `.behindWindow`)
  with the WKWebView on top, WKWebView background transparent
  (`webView.setValue(false, forKey: "drawsBackground")`) so the page CSS (translucent
  background, ~0.8 effective opacity) composites over the vibrancy.
- Size: start ~560 × 640 (composer + a few turns visible). Growing-with-content is a stretch
  goal (Phase 5); fixed size with internal scroll is the Phase 4 artifact.
- Position: top-center of the screen containing the mouse (`NSEvent.mouseLocation` →
  `NSScreen`) with a ~15% top margin. Re-position on every show.
- Dismiss: Escape key, and `resignKey`/click-outside (observe `NSApplication.didResignKeyActiveNotification`
  → orderOut). Re-hotkey toggles (show if hidden, hide if shown and key).
- Dark/light: vibrancy adapts automatically; page CSS uses `prefers-color-scheme` — dark default.

### 6.5 WKWebView specifics

- Load `http://localhost:8765/app` (+ `#capture=<id>` when a capture is in flight). Same
  origin as every API call → no CORS, no cookies needed.
- App Transport Security: HTTP to `localhost` — add `NSAppTransportSecurity →
  NSAllowsLocalNetworking = YES` in Info.plist to be safe across macOS versions.
- **RISK GATE — verify `fetch` + `ReadableStream` streaming inside WKWebView early (first
  task of Phase 4).** WKWebView historically lagged WebKit/Safari on streaming fetch. If
  SSE-over-fetch does not stream in WKWebView: fallback = native SSE in Swift
  (`URLSession` bytes task) bridged into the page via `WKScriptMessageHandler`
  (`window.webkit.messageHandlers.sse.postMessage` / `evaluateJavaScript` dispatching a
  `CustomEvent` the page listens for). The page should already isolate its SSE parsing behind
  one function so the bridge can replace the transport. Test with a minimal probe page FIRST
  (one fetch to `/api/health` streamed through a dummy SSE endpoint) before building the whole
  panel on the assumption it works.
- **RESOLVED (verified working — no bridge needed):** WKWebView on this machine
  (macOS 26.6, Xcode 27) delivers `fetch` + `ReadableStream` SSE progressively —
  the probe measured 10 tokens arriving at ~300 ms gaps matching server pacing
  exactly. Probe harness: `paper-agent-swift-app/probe/probe.swift` +
  `/app/probe.html` (dummy endpoint `GET /api/sse-probe`). Two gotchas for future
  probes: WKWebView caches aggressively (cache-bust probe URLs with a query
  param), and the daemon sends `\r\n\r\n` event separators (normalize before
  splitting on `\n\n` — `sse.js` already does).
- `localStorage` works in WKWebView (page can persist trivial prefs: composer height, etc.).

### 6.6 Settings

- UserDefaults (`defaults write com.vibhu.paperagent …`): `daemonUrl` (default
  `http://localhost:8765`), `hotkey` (default Cmd+Shift+P). Menu-bar "Settings…" panel is
  Phase 5 polish; defaults + a simple in-menu display suffice earlier.

---

## 7. Permissions, gotchas, and honest constraints (READ BEFORE PHASE 4)

### 7.1 TCC permissions — the #1 new-session time sink

The Swift app needs grants Raycast already had. Expect macOS prompts; the plan must make them
appear deliberately, not mid-demo:

1. **Accessibility** (System Settings → Privacy → Accessibility) — for the AX selection read
   and the System Events keystroke fallback. Detect-and-guide: `AXIsProcessTrustedWithOptions`
   with the prompt flag; menu-bar item shows "Grant Accessibility…" until granted.
2. **Automation / Apple Events** — per target app: Chrome, Safari, System Events. First
   `NSAppleScript` to each → TCC prompt → user clicks OK. The app should catch the
   `errAEEventNotPermitted` (-1743) error and surface "Allow controlling Chrome in System
   Settings → Privacy → Automation" instead of failing silently.

### 7.2 Hotkey conflict during coexistence

Raycast currently owns Cmd+Shift+P. During Phases 4–5 bind the Swift app a throwaway hotkey
(e.g. Cmd+Ctrl+Shift+P). Only at Phase 6 cutover: remove the Raycast hotkey, then set the
Swift hotkey to Cmd+Shift+P. Registering a Carbon hotkey that collides silently fails —
always verify the registration result and log it.

### 7.3 Operational gotchas carried over from the Raycast era

- Daemon must run from the project root (`.env` discovery) or every ask 503s with
  "OPENROUTER_API_KEY is not set."
- Stale daemon on 8765 — check `lsof -nP -iTCP:8765`.
- The daemon is not auto-started at login (D8): a login hotkey press with no daemon = the
  panel shows the daemon-down state. Menu-bar icon reflects this. Follow-up (§9): LaunchAgent
  for the daemon itself.
- **App Nap (verified the hard way):** an LSUIElement app whose panel is ordered out gets
  napped — timers/network suspend, the page's fetches fail (misread as "daemon not
  reachable"), and recovery polls fire in coalesced bursts. Fixed by holding a
  `ProcessInfo.beginActivity(.userInitiatedAllowingIdleSystemSleep)` assertion for the
  app's lifetime (AppCore). Do not remove it.

### 7.4 Known trade-offs accepted by the user

- Clipboard fallback clobbers the user's clipboard (existing behavior; optionally save/restore
  the pasteboard around the keystroke — Phase 5 polish, flagged).
- AX selection read may fail in some apps → falls to browser JS/clipboard; non-browser apps
  without AX selection yield "no selection" captures (active-paper fallback) — same as today.
- Vibrancy blur behind a web view is ~95% native feel, not pixel-perfect NSVisualEffectView
  rendering of the page itself (the page background must stay translucent for the effect).

### 7.5 Security notes (repo rules)

- Never read/print `.env`. The Swift app never sees any API key — it only talks to the daemon.
- `PAPER_AGENT_SECRET` stays server-side only; the page never performs destructive operations
  (no purge/delete UI — deliberately out of scope).

---

## 8. Phased build plan (each phase ends in a testable artifact)

Work strictly in phase order. Do not start a phase before the previous one's verification
passes. A new session should be able to resume at any phase boundary using only this doc + the
repo.

### Phase 0 — Plan + scaffold (this document)

- Artifact: this file, committed at `paper-agent-swift-app/migration_plan.md`.
- Verify: doc review with the user. No code.

### Phase 1 — Daemon additions (Layer 1)

- Tasks: static mount `/app` serving `paper_agent/webapp/` (empty placeholder index.html is
  fine here); `POST /api/capture` + `GET /api/capture/{id}` with TTL + cap.
- Files: `paper_agent/api/server.py` (+ `paper_agent/webapp/index.html` placeholder).
- Verify: §4.4 curl checklist.
- Effort: ~1 hour.

### Phase 2 — The web page, complete (Layer 2)

- Tasks: full `index.html` per §5 — capture fetch, resolve preview, composer, toggle,
  transcript, SSE parsing, paper override picker, vendored markdown renderer, error states,
  daemon-down handling. Optional PWA manifest.
- Files: `paper_agent/webapp/` only. Zero Swift, zero daemon changes.
- Verify: §5.6 browser checklist (8 scenarios). This is the first user-visible win — the page
  is already usable as a daily driver in a browser tab at this point.
- Effort: ~half a day.

### Phase 3 — Swift skeleton: menu bar + panel + page (Layer 3 start)

- Tasks: Xcode project; MenuBarExtra with health-poll icon; NSPanel (fixed size, basic
  vibrancy); persistent WKWebView loading `/app`; ATS exception; Open Panel menu action.
  **First task inside this phase: the WKWebView SSE-streaming probe (§6.5 risk gate)** —
  if streaming is broken, implement the URLSession→WKScriptMessage bridge NOW and note it in
  this doc (§6.5) for future sessions.
- Verify: run from Xcode → menu-bar icon appears (green when daemon up) → Open Panel → page
  loads → **full ask flow works inside the panel, streaming** (test all 8 scenarios of §5.6
  inside the panel, not just in Chrome).
- Effort: ~half a day (probe included).

### Phase 4 — Hotkey + capture + handoff (the parity milestone)

- Tasks: Carbon hotkey (throwaway combo, §7.2); CaptureService ladder (§6.3) with permission
  detection/guidance (§7.1); handoff POST → `#capture=<id>` reload; capture-before-show
  ordering; Escape/click-outside dismiss; re-hotkey toggle.
- Verify (manual, scripted):
  1. Chrome arXiv page, select paragraph → hotkey → panel with quote → ask → grounded answer.
  2. Same section follow-up → continues; other section → fresh (toggle label honest).
  3. Chrome PDF viewer selection (clipboard path) → quote captured.
  4. Safari page → URL + selection captured.
  5. Preview PDF with no URL → no-selection capture → active-paper fallback (or picker).
  6. Unknown URL → ingesting banner → auto-ingested answer.
  7. No daemon running → panel shows daemon-down state, menu icon gray.
  8. Accessibility not granted → app guides user; browser URL capture still works.
  9. Raycast still functional alongside (parallel run).
- At this point the Swift app does everything the Raycast ask flow does. Dogfood starts here
  (keep Raycast bound as backup).
- Effort: ~1 day (permissions prompting eats time).

### Phase 5 — Polish

- Tasks: window grows with transcript content (or comfortable fixed height — decide by feel);
  final vibrancy/opacity pass; clipboard save/restore around the Cmd+C fallback; hotkey
  configurability + settings surface; launch-at-login (SMAppService); app icon; "New Thread"
  menu action; multi-display positioning refinement; edge cases (very long quotes → clamp
  display, full text on hover/expand).
- Verify: a full day of real reading sessions through the panel only; Raycast untouched as
  the safety net.
- Effort: ~1 day, optional items trimmable.

### Phase 6 — Cutover

- Tasks: remove Raycast "Capture & Ask" hotkey binding; set Swift hotkey to Cmd+Shift+P;
  launch-at-login ON; final dogfood week. Keep the raycast extension code in-repo (do NOT
  delete `raycast-extensions/` — it remains a working fallback and reference; decide on
  removal only after weeks of stable panel use). Update `outputs.md` + `AGENTS.md` with the
  new architecture and the `paper-agent-swift-app/` build/run instructions.
- Verify: one week with zero Raycast usage; panel survived restarts, login, permission
  prompts, daemon restarts.
- Rollback: rebind Raycast hotkey (extension never stopped working). Instant.

---

## 9. Things the original discussion missed (added during planning)

1. **TCC permission matrix** (§7.1) — Accessibility + per-app Automation grants are the real
   migration tax; Raycast had them, the new app must earn them.
2. **WKWebView streaming risk** (§6.5) — the single technical unknown; probed early with a
   designed fallback bridge.
3. **Daemon auto-start** — neither Raycast nor the panel starts the daemon. Follow-up after
   cutover: a user LaunchAgent running `paper-agent serve` at login (uv from the repo venv).
   Not in scope, logged here so it isn't forgotten.
4. **Hotkey collision management** during coexistence (§7.2).
5. **Panel persistence** — transcript survives hide/show only if the WKWebView is never
   destroyed (D5); this is a deliberate architectural constraint, not an optimization.
6. **Error-state matrix** — daemon down / API key missing (503 detail) / ingestion failed /
   network dropped mid-stream. Each has a designed UI state in §5; the page must never white-screen.
7. **Cross-space retarget** — the `resolved` SSE event can change the active space mid-stream;
   the page must update its ask URL target (ask.tsx already handles this; port it).
8. **Clipboard clobber** in the PDF capture path — same as today, but now we can fix it
   (save/restore) since we own the native layer (Phase 5).
9. **Session browsing** — `session-history.tsx` has no page equivalent yet. Optional Phase 5+
   addition: a small "history" mode in the page consuming the existing sessions endpoints.
   Obsidian remains the long-form reader.
10. **Update story** — the app is local-only: rebuild via Xcode, ad-hoc signed, no notarization,
    no Sparkle. Log it so nobody looks for a distribution pipeline that doesn't exist.

---

## 10. Open questions (decide at the relevant phase, not now)

- Phase 5: fixed panel height vs growing-with-content (decide by feel during dogfood).
- Phase 5+: absorb session browsing into the page, or leave it to Obsidian/Raycast-fallback?
- Post-cutover: delete the raycast extension repo dir eventually, or keep as reference forever?
- Should the menu-bar app ever show transient answers as macOS notifications (no — current
  design says the panel is the only surface; revisit only if the panel proves annoying).

## 11. Definition of done

The migration is complete when, for one continuous week:

- Every ask happens through the Swift panel (hotkey → quote → question → streamed answer →
  saved to vault), with Raycast's hotkey unbound and the extension untouched-but-unused.
- The panel survives: app relaunch, logout/login (launch-at-login), daemon restarts, permission
  re-prompts after macOS updates.
- Obsidian still shows the same vault artifacts (sessions, summaries, knowledge) — proving
  nothing downstream changed.
- `outputs.md` and `AGENTS.md` describe the new architecture accurately.
