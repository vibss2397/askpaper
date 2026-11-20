/* Paper Agent panel page — app logic (migration plan §5).
 * State model per §5.4. All asks/resolves go to the daemon on the same origin. */
"use strict";

/* ── state (§5.4) ─────────────────────────────────────────────────────── */

const state = {
  capture: null,        /* {selected_text, source_app, source_title, source_url} */
  resolve: null,        /* last /api/resolve response */
  activeSpace: "",      /* space used in the ask URL path (cross-space retargetable) */
  resolvedPaper: null,  /* {paper_id, title} from resolve / `resolved` SSE event */
  overridePaper: null,  /* explicit user pick from the paper picker */
  turns: [],            /* [{question, answer, sessionPath, section, continued, error}] */
  streaming: null,      /* in-flight turn */
  freshChoice: null,    /* null = mirror resolve; true/false = explicit user choice */
  daemonUp: null,
  threadInfo: null,     /* last `thread` SSE event {section, continued} */
};

/* ── tiny helpers ─────────────────────────────────────────────────────── */

const $ = (id) => document.getElementById(id);

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}

async function fetchJson(path, opts) {
  try {
    const res = await fetch(path, opts);
    if (!res.ok) return null;
    return await res.json();
  } catch (_) {
    return null;
  }
}

/* ── markdown (marked is vendored; sanitize a basic strip of script/onClick) ── */

const BAD_TAGS = new Set(["script", "style", "iframe", "object", "embed", "link", "meta", "base", "form"]);

function sanitizeHtml(html) {
  const tpl = document.createElement("template");
  tpl.innerHTML = html;
  const walker = document.createTreeWalker(tpl.content, NodeFilter.SHOW_ELEMENT);
  const remove = [];
  let node;
  while ((node = walker.nextNode())) {
    if (BAD_TAGS.has(node.tagName.toLowerCase())) {
      remove.push(node);
      continue;
    }
    for (const attr of Array.from(node.attributes)) {
      const name = attr.name.toLowerCase();
      /* URL parsers strip tab/LF/CR inside schemes ("java\tscript:" runs), so
       * remove control chars before the scheme check. data: is blocked except
       * for inline images. */
      const raw = (attr.value || "").replace(/[\s\u0000-\u001f]/g, "").toLowerCase();
      if (name.startsWith("on") || raw.startsWith("javascript:") ||
          (raw.startsWith("data:") && !raw.startsWith("data:image/"))) {
        node.removeAttribute(attr.name);
      }
    }
  }
  for (const n of remove) n.remove();
  return tpl.innerHTML;
}

function renderMarkdown(text) {
  if (typeof marked !== "undefined" && marked.parse) {
    return sanitizeHtml(marked.parse(text));
  }
  return sanitizeHtml(
    String(text).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])).replace(/\n/g, "<br>")
  );
}

/* ── continue/fresh toggle (§5.1, §5.2) ────────────────────────────────── */

function effectiveFresh() {
  if (state.freshChoice !== null) return state.freshChoice;
  const r = state.resolve;
  if (r && r.found && r.thread_state === "continuing") return false;
  return true;
}

function toggleLabel() {
  const r = state.resolve;
  if (!effectiveFresh()) {
    const sec = r && r.section ? " · §" + r.section : "";
    const n = r && r.found && r.qa_count ? " · " + r.qa_count + " Q&A" : "";
    return "Continue thread" + sec + n;
  }
  if (state.freshChoice === true && r && r.found && r.thread_state === "continuing") {
    return "Fresh thread · forced (history will NOT be used)";
  }
  if (!r) return "Fresh thread";
  if (!r.found) {
    if (r.thread_state === "new_paper") return "Fresh thread · new paper will be ingested";
    return "Fresh thread · no paper (selection only)";
  }
  return r.section ? "Fresh thread · §" + r.section : "Fresh thread";
}

function renderToggle() {
  $("continue-toggle").checked = !effectiveFresh();
  $("toggle-label").textContent = toggleLabel();
}

/* ── renderers ────────────────────────────────────────────────────────── */

function renderQuote() {
  const box = $("quote-box");
  const c = state.capture;
  if (!c || !String(c.selected_text || "").trim()) {
    box.hidden = true;
    return;
  }
  box.hidden = false;
  $("quote-text").textContent = c.selected_text;
  const meta = [c.source_app, c.source_title].filter(Boolean).join(" · ");
  $("quote-meta").textContent = meta;
  $("quote-meta").hidden = !meta;
}

function renderThreadHeader() {
  const h = $("thread-header");
  const paper = state.overridePaper || state.resolvedPaper;
  const bits = [];
  if (paper && paper.title) bits.push(paper.title + (state.overridePaper ? " (manual)" : ""));
  if (state.activeSpace) bits.push(state.activeSpace);
  const ti = state.threadInfo;
  if (ti) {
    bits.push(ti.continued ? (ti.section ? "continuing §" + ti.section : "continuing") : "fresh");
  }
  if (bits.length === 0) {
    h.hidden = true;
    return;
  }
  h.hidden = false;
  h.textContent = bits.join(" · ");
}

function renderPlaceholder() {
  const c = state.capture;
  const r = state.resolve;
  let p = "What would you like to know?";
  if (String((c && c.selected_text) || "").trim()) p = "Reply to this section…";
  else if (r && r.found && r.thread_state === "continuing" && !effectiveFresh()) p = "Continue the conversation…";
  $("question").placeholder = state.streaming ? "Answering…" : p;
}

function renderPickerButton() {
  const btn = $("paper-picker-btn");
  if (!state.activeSpace) {
    btn.hidden = true;
    return;
  }
  btn.hidden = false;
  btn.textContent = state.overridePaper
    ? "paper: " + state.overridePaper.title + " ▾"
    : "paper ▾";
}

function emptyStateText() {
  if (!state.activeSpace) {
    return "No spaces yet — create one with: uv run paper-agent init --space <name>";
  }
  return "No questions yet. Ask something above.";
}

function turnNode(t) {
  const node = el("div", "turn");
  node.appendChild(el("div", "q", t.question));
  if (String(t.answer || "").trim()) {
    const a = el("div", "a");
    a.innerHTML = renderMarkdown(t.answer);
    node.appendChild(a);
  }
  if (t.error) node.appendChild(el("div", "error", t.error));
  if (t.sessionPath) {
    const file = String(t.sessionPath).split("/").pop();
    node.appendChild(el("div", "foot", "Saved to vault · " + file));
  }
  const copy = el("button", "copy", "Copy");
  copy.type = "button";
  copy.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(t.answer || "");
      copy.textContent = "Copied";
      setTimeout(() => (copy.textContent = "Copy"), 1200);
    } catch (_) {}
  });
  node.appendChild(copy);
  return node;
}

function renderTurns() {
  const box = $("turns");
  box.innerHTML = "";
  if (state.turns.length === 0 && !state.streaming) {
    box.appendChild(el("div", "empty", emptyStateText()));
    return;
  }
  for (const t of state.turns) box.appendChild(turnNode(t));
}

function renderAll() {
  renderQuote();
  renderToggle();
  renderThreadHeader();
  renderPlaceholder();
  renderPickerButton();
  renderTurns();
}

/* ── transcript scrolling: auto-scroll while pinned to bottom ──────────── */

let autoScroll = true;

function maybeScrollToBottom() {
  if (autoScroll) {
    const sc = $("transcript");
    sc.scrollTop = sc.scrollHeight;
  }
}

/* ── daemon health (§5.6 scenario 7: never a blank screen, auto-recover) ── */

async function ping() {
  try {
    const res = await fetch("/api/health", { cache: "no-store" });
    return res.ok;
  } catch (err) {
    console.error("[paper-agent] health fetch failed:", err && err.message ? err.message : err);
    state.lastDaemonError = err && err.message ? err.message : "network error";
    return false;
  }
}

let pollTimer = null;

function renderDaemonBanner() {
  $("daemon-banner").hidden = state.daemonUp !== false;
  const msg = $("daemon-msg");
  if (msg) msg.textContent = state.lastDaemonError ? " (" + state.lastDaemonError + ")" : "";
}

function markDaemonDown(reason) {
  if (reason) state.lastDaemonError = reason;
  logState("MARK-DAEMON-DOWN: " + (reason || state.lastDaemonError || "no reason"));
  if (state.daemonUp !== false) {
    state.daemonUp = false;
    renderDaemonBanner();
  }
  scheduleRecoveryPoll();
}

function scheduleRecoveryPoll() {
  if (pollTimer) return;
  const tick = async () => {
    if (await ping()) {
      pollTimer = null;
      state.daemonUp = true;
      logState("RECOVERED");
      renderDaemonBanner();
      bootstrap();
    } else {
      pollTimer = setTimeout(tick, 5000);
    }
  };
  pollTimer = setTimeout(tick, 5000);
}

/* ── page-state logging (piped to the Swift app's stdout — §7.3 debugging) ── */

function logState(event) {
  try {
    console.log("[paper-agent] " + event +
      " | daemonUp=" + state.daemonUp +
      " | lastError=" + (state.lastDaemonError || "none") +
      " | space=" + (state.activeSpace || "?") +
      " | thread=" + (state.resolve && state.resolve.found ? state.resolve.thread_state + "/qa" + state.resolve.qa_count : "none"));
  } catch (_) {}
}

/* ── resolve / hydration (§5.2) ────────────────────────────────────────── */

async function refreshResolve(seed) {
  const c = state.capture || {};
  let r;
  try {
    const res = await fetch("/api/resolve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source_url: c.source_url || "", selected_text: c.selected_text || "" }),
    });
    if (!res.ok) return;
    r = await res.json();
  } catch (err) {
    console.error("[paper-agent] resolve fetch failed:", err && err.message ? err.message : err);
    markDaemonDown(err && err.message ? "resolve: " + err.message : "resolve: network error");
    return;
  }
  /* Rendering happens OUTSIDE the try/catch: a DOM bug must never be
   * misreported as "daemon not reachable". */
  state.resolve = r;
  logState("RESOLVE-OK");
  if (r.found) {
    if (r.space) state.activeSpace = r.space;
    state.resolvedPaper = {
      paper_id: r.paper_id,
      title: r.title || r.paper_id,
    };
    if (seed) {
      state.overridePaper = null;
      const qa = r.recent_qa || [];
      state.turns = qa.slice(-10).map((x) => ({
        question: x.question,
        answer: x.answer,
        sessionPath: "",
        section: x.section || "",
        continued: null,
        error: null,
      }));
    }
  } else if (seed) {
    state.resolvedPaper = null;
    state.overridePaper = null;
    state.turns = [];
  }
  renderAll();
}

async function bootstrap() {
  const ctx = await fetchJson("/api/context");
  const spaces = await fetchJson("/api/spaces");
  let space = (ctx && ctx.last_space) || "";
  if (!space && Array.isArray(spaces) && spaces.length > 0) space = spaces[0].name;
  state.activeSpace = space || "";
  await refreshResolve(true);
}

/* ── capture handoff (§4.2 / D4): /app#capture=<id> ────────────────────── */

function captureIdFromHash() {
  const m = (location.hash || "").match(/^#capture=([A-Za-z0-9_-]+)/);
  return m ? m[1] : null;
}

async function consumeCapture() {
  const id = captureIdFromHash();
  if (!id) return;
  history.replaceState(null, "", location.pathname);
  const cap = await fetchJson("/api/capture/" + encodeURIComponent(id), { cache: "no-store" });
  if (cap) {
    state.capture = cap;
    state.freshChoice = null;
    state.threadInfo = null;
  }
}

window.addEventListener("hashchange", async () => {
  if (!captureIdFromHash()) return;
  console.log("[paper-agent] HASHCHANGE-CAPTURE " + captureIdFromHash());
  await consumeCapture();
  await refreshResolve(true);
});

/* ── ask + SSE streaming (§5.3) ────────────────────────────────────────── */

function setComposerBusy(busy) {
  const ta = $("question");
  ta.disabled = !!busy;
  renderPlaceholder();
  if (!busy) ta.focus();
}

function renderStreaming() {
  const box = $("streaming");
  const s = state.streaming;
  if (!s) {
    box.innerHTML = "";
    box.hidden = true;
    return;
  }
  box.hidden = false;
  box.innerHTML = "";
  const node = el("div", "turn streaming");
  node.appendChild(el("div", "q", s.question));
  const banner = el("div", "banner");
  banner.id = "stream-banner";
  banner.hidden = !s.banner;
  if (s.banner) banner.textContent = s.banner;
  node.appendChild(banner);
  const a = el("div", "a");
  a.id = "stream-answer";
  if (s.partial) {
    a.innerHTML = renderMarkdown(s.partial);
    a.classList.add("cursor");
  } else {
    a.classList.add("waiting");
  }
  node.appendChild(a);
  const err = el("div", "error");
  err.id = "stream-error";
  err.hidden = !s.error;
  if (s.error) err.textContent = s.error;
  node.appendChild(err);
  box.appendChild(node);
  maybeScrollToBottom();
}

function updateStreamingAnswer() {
  const s = state.streaming;
  if (!s) return;
  const a = $("stream-answer");
  if (!a) return;
  if (s.partial) {
    a.classList.remove("waiting");
    a.classList.add("cursor");
    a.innerHTML = renderMarkdown(s.partial);
  }
  maybeScrollToBottom();
}

function updateStreamingBanner() {
  const s = state.streaming;
  if (!s) return;
  const b = $("stream-banner");
  if (!b) return;
  b.hidden = !s.banner;
  if (s.banner) b.textContent = s.banner;
}

function updateStreamingError() {
  const s = state.streaming;
  if (!s) return;
  const e = $("stream-error");
  if (!e) return;
  e.hidden = !s.error;
  if (s.error) e.textContent = s.error;
}

function handleEventData(data) {
  const s = state.streaming;
  if (!s) return;
  const evt = SSE.classifyEvent(data, s.errorPending);
  switch (evt.type) {
    case "token":
      s.partial += evt.text;
      updateStreamingAnswer();
      break;
    case "status": {
      const o = evt.obj;
      if (o.status === "resolved") {
        if (o.space) state.activeSpace = o.space; /* cross-space retarget (§9.7) */
        if (o.paper) state.resolvedPaper = o.paper;
        renderThreadHeader();
        renderPickerButton();
      } else if (o.status === "thread") {
        state.threadInfo = { section: o.section || "", continued: !!o.continued };
        s.section = o.section || "";
        s.continued = !!o.continued;
        renderThreadHeader();
      } else if (o.status === "ingesting") {
        s.banner = o.message || "Downloading and converting paper…";
        updateStreamingBanner();
      } else if (o.status === "ingested") {
        s.banner = null;
        if (o.paper_id) {
          state.resolvedPaper = { paper_id: o.paper_id, title: o.title || o.paper_id };
          renderThreadHeader();
          renderPickerButton();
        }
        updateStreamingBanner();
      } else if (o.status === "ingest_failed") {
        s.banner = "Ingestion failed — falling back to selected text (" + o.error + ")";
        updateStreamingBanner();
      }
      break;
    }
    case "session_path":
      s.sessionPath = evt.path;
      break;
    case "error_sentinel":
      s.errorPending = true;
      break;
    case "error_detail":
      s.error = evt.message;
      updateStreamingError();
      break;
    case "done":
      break;
  }
}

function finishStream(ok) {
  const s = state.streaming;
  if (!s) return;
  state.streaming = null;
  state.turns.push({
    question: s.question,
    answer: s.partial,
    sessionPath: s.sessionPath,
    section: s.section,
    continued: s.continued,
    error: s.error || null,
  });
  if (ok) {
    state.freshChoice = null; /* next ask mirrors fresh resolve truth */
  }
  setComposerBusy(false);
  renderTurns();
  $("streaming").innerHTML = "";
  $("streaming").hidden = true;
  renderPlaceholder();
  maybeScrollToBottom();
  if (ok) refreshResolve(false); /* re-preview the toggle for the next turn */
}

function failStream(detail) {
  const s = state.streaming;
  if (!s) return;
  s.error = detail + "\n\nIs the daemon running? uv run paper-agent serve --port 8765";
  updateStreamingError();
  finishStream(false);
}

async function ask(question) {
  const c = state.capture || {};
  const payload = {
    question: question,
    selected_text: c.selected_text || "",
    source_app: c.source_app || "",
    source_title: c.source_title || "",
    source_url: c.source_url || "",
    fresh: effectiveFresh(),
  };
  if (state.overridePaper) payload.paper_id = state.overridePaper.paper_id;

  state.streaming = {
    question: question,
    partial: "",
    banner: null,
    sessionPath: "",
    section: "",
    continued: null,
    error: null,
    errorPending: false,
  };
  state.threadInfo = null;
  setComposerBusy(true);
  renderThreadHeader();
  renderStreaming();
  autoScroll = true;
  maybeScrollToBottom();

  let buffer = "";
  try {
    const res = await fetch("/api/spaces/" + encodeURIComponent(state.activeSpace) + "/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      let detail = res.status + " " + res.statusText;
      try {
        const j = await res.json();
        if (j && j.detail) detail = j.detail;
      } catch (_) {}
      failStream(detail);
      return;
    }

    const reader = res.body ? res.body.getReader() : null;
    if (!reader) {
      failStream("No response body received.");
      return;
    }
    const decoder = new TextDecoder();
    for (;;) {
      const r = await reader.read();
      if (r.done) break;
      const fed = SSE.sseFeed(buffer, decoder.decode(r.value, { stream: true }));
      buffer = fed.buffer;
      for (const data of fed.events) handleEventData(data);
    }
    finishStream(true);
  } catch (err) {
    const msg = err && err.message ? err.message : "Network error";
    console.error("[paper-agent] ask failed:", msg);
    markDaemonDown("ask: " + msg);
    failStream(msg);
  }
}

/* ── composer ─────────────────────────────────────────────────────────── */

function autosize() {
  const ta = $("question");
  ta.style.height = "auto";
  ta.style.height = Math.min(ta.scrollHeight, 160) + "px";
}

function submitQuestion() {
  const ta = $("question");
  const q = ta.value.trim();
  if (!q || state.streaming) return;
  if (!state.activeSpace) {
    const box = $("turns");
    box.innerHTML = "";
    box.appendChild(el("div", "empty", emptyStateText()));
    return;
  }
  ta.value = "";
  autosize();
  ask(q);
}

$("composer").addEventListener("submit", (e) => {
  e.preventDefault();
  submitQuestion();
});

$("question").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    submitQuestion();
  }
});

$("question").addEventListener("input", autosize);

/* ── toggle (§5.2: flip back to continue → re-preview) ─────────────────── */

$("continue-toggle").addEventListener("change", () => {
  const fresh = !$("continue-toggle").checked;
  state.freshChoice = fresh;
  renderToggle();
  renderPlaceholder();
  if (!fresh) refreshResolve(false);
});

/* ── quote expand ─────────────────────────────────────────────────────── */

$("quote-box").addEventListener("click", () => {
  $("quote-box").classList.toggle("expanded");
});

/* ── paper override picker (D3: only override, space is never chosen) ──── */

async function openPaperMenu() {
  const menu = $("paper-menu");
  const btn = $("paper-picker-btn");
  const papers = await fetchJson(
    "/api/spaces/" + encodeURIComponent(state.activeSpace) + "/papers",
    { cache: "no-store" }
  );
  menu.innerHTML = "";

  const auto = el("div", "pm-item");
  auto.appendChild(el("span", "pm-title", "Auto — server decides (from URL)"));
  auto.appendChild(el("span", "pm-type", ""));
  if (!state.overridePaper) auto.classList.add("pm-selected");
  auto.addEventListener("click", () => {
    state.overridePaper = null;
    closePaperMenu();
    renderPickerButton();
    renderThreadHeader();
  });
  menu.appendChild(auto);

  for (const p of papers || []) {
    const item = el("div", "pm-item");
    item.appendChild(el("span", "pm-title", p.title || p.paper_id));
    item.appendChild(el("span", "pm-type", p.type || ""));
    if (state.overridePaper && state.overridePaper.paper_id === p.paper_id) item.classList.add("pm-selected");
    item.addEventListener("click", () => {
      state.overridePaper = { paper_id: p.paper_id, title: p.title || p.paper_id };
      closePaperMenu();
      renderPickerButton();
      renderThreadHeader();
    });
    menu.appendChild(item);
  }

  const rect = btn.getBoundingClientRect();
  menu.style.left = Math.max(8, Math.min(rect.left, window.innerWidth - 300)) + "px";
  menu.style.top = rect.bottom + 6 + "px";
  menu.hidden = false;
}

function closePaperMenu() {
  $("paper-menu").hidden = true;
}

$("paper-picker-btn").addEventListener("click", (e) => {
  e.stopPropagation();
  if ($("paper-menu").hidden) openPaperMenu();
  else closePaperMenu();
});

document.addEventListener("click", (e) => {
  const menu = $("paper-menu");
  if (!menu.hidden && !menu.contains(e.target)) closePaperMenu();
});

document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  const menu = $("paper-menu");
  if (!menu.hidden) {
    closePaperMenu();
    return;
  }
  /* Inside the Swift panel: hand Escape to the native layer to hide the panel
   * (the native key monitor was removed — see PanelController). */
  if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.panel) {
    window.webkit.messageHandlers.panel.postMessage("escape");
  }
});

/* ── transcript scroll pinning ────────────────────────────────────────── */

$("transcript").addEventListener("scroll", () => {
  const sc = $("transcript");
  autoScroll = sc.scrollHeight - sc.scrollTop - sc.clientHeight < 48;
});

/* ── retry button ─────────────────────────────────────────────────────── */

$("retry").addEventListener("click", async () => {
  if (await ping()) {
    state.daemonUp = true;
    logState("RETRY-OK");
    renderDaemonBanner();
    bootstrap();
  } else {
    markDaemonDown("retry ping failed");
  }
});

/* Surface any uncaught page error in the log pipeline (WKWebView pipes
 * console.* to the Swift app's stdout). */
window.addEventListener("error", (e) => {
  console.error("[paper-agent] page error:", e.message, e.filename + ":" + e.lineno);
});
window.addEventListener("unhandledrejection", (e) => {
  const r = e.reason;
  console.error("[paper-agent] unhandled rejection:", r && r.message ? r.message : String(r));
});

/* ── init ─────────────────────────────────────────────────────────────── */

async function init() {
  logState("INIT");
  renderAll();
  await consumeCapture();
  logState("CAPTURE-CONSUMED");
  if (await ping()) {
    state.daemonUp = true;
    logState("INIT-PING-OK");
    renderDaemonBanner();
    await bootstrap();
  } else {
    markDaemonDown("init ping failed");
  }
}

document.addEventListener("DOMContentLoaded", init);

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}
