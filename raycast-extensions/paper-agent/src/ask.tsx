import {
  Action,
  ActionPanel,
  Detail,
  Form,
  List,
  getPreferenceValues,
  LocalStorage,
  showToast,
  Toast,
  LaunchProps,
  useNavigation,
} from "@raycast/api";
import { useState, useEffect, useRef } from "react";
import { captureContext, type Source } from "./capture";
import type { AskLaunchContext } from "./capture-and-ask";

// ── Types ──────────────────────────────────────────────────────────────────

interface Space {
  name: string;
  sessions: number;
}

interface PaperRow {
  paper_id: string;
  title: string;
  type: string;
}

interface ResolvedPaper {
  paper_id: string;
  title: string;
}

interface ResolvedThread {
  found: boolean;
  space?: string;
  paper_id?: string;
  title?: string;
  qa_count?: number;
  recent_qa?: { id: string; question: string; answer: string; section: string }[];
  thread_state?: "continuing" | "fresh" | "new_paper" | "no_paper";
  section?: string;
}

interface ThreadState {
  state: "continuing" | "fresh" | "new_paper" | "no_paper";
  section: string;
}

const NO_PAPER_STATE: ThreadState = { state: "no_paper", section: "" };

interface Turn {
  question: string;
  answer: string;
}

interface ThreadInfo {
  section: string;
  continued: boolean;
}

interface AskPayload {
  question: string;
  selected_text: string;
  source_app: string;
  source_title: string;
  source_url: string;
  fresh: boolean;
  paper_id?: string;
}

interface ActiveAsk {
  id: number;
  payload: AskPayload;
}

interface Preferences {
  daemonUrl: string;
  defaultSpace: string;
}

const EMPTY_SOURCE: Source = { app: "", title: "", url: "" };

// ── Helpers ────────────────────────────────────────────────────────────────

function prefs(): Preferences {
  return getPreferenceValues<Preferences>();
}

function daemon(path: string): string {
  const base = prefs().daemonUrl.replace(/\/+$/, "");
  return `${base}${path}`;
}

async function fetchJson<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(daemon(path));
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

function buildTranscript(
  space: string,
  paperTitle: string,
  turns: Turn[],
  threadInfo: ThreadInfo | null,
  currentQuestion: string | null,
  streamingAnswer: string,
  banner: string | null,
): string {
  const bits: string[] = [];
  if (paperTitle) bits.push(paperTitle);
  if (threadInfo?.continued && threadInfo.section) bits.push(`continuing §${threadInfo.section}`);
  const header = bits.length > 0 ? `*${bits.join(" ·")}*\n\n---\n\n` : "";

  let body = "";
  for (const t of turns) {
    body += `**You:** ${t.question}\n\n${t.answer}\n\n---\n\n`;
  }

  if (currentQuestion !== null) {
    body += `**You:** ${currentQuestion}\n\n`;
    if (banner) body += `> ${banner}\n\n`;
    body += streamingAnswer || "…";
  }

  if (!body) body = "_No questions yet._";

  return header + body.trimEnd();
}

function stripMarkdown(s: string): string {
  return s
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/^#{1,6}\s*/gm, "")
    .replace(/^>\s*/gm, "")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\s*\n+\s*/g, " · ")
    .trim();
}

function threadPreview(turns: Turn[], maxTurns = 5, answerLen = 200): string {
  return turns
    .slice(-maxTurns)
    .map((t) => {
      const a = stripMarkdown(t.answer);
      const clipped = a.length > answerLen ? `${a.slice(0, answerLen)}…` : a;
      return `Q: ${stripMarkdown(t.question)}\nA: ${clipped}`;
    })
    .join("\n\n");
}

function statusText(threadState: ThreadState, forceFresh: boolean, priorCount: number): string {
  if (forceFresh) return "○ forced fresh — history will NOT be used (⌘N to undo)";
  switch (threadState.state) {
    case "continuing":
      return `● continuing §${threadState.section || "?"} — ${priorCount} prior Q&A in this thread`;
    case "fresh":
      return "○ fresh thread — selection is in a different section";
    case "new_paper":
      return "○ new paper — will be downloaded & ingested on ask";
    default:
      return "○ no paper — answer from selection only";
  }
}

function quoteText(selectedText: string, maxLen = 140): string {
  const clipped =
    selectedText.length > maxLen ? `${selectedText.slice(0, maxLen)}…` : selectedText;
  return `"${clipped}"`;
}

// ── Paper Picker (leaf view for explicit override) ─────────────────────────

function PaperPicker({
  space,
  onPick,
}: {
  space: string;
  onPick: (paper: ResolvedPaper | null) => void;
}) {
  const [papers, setPapers] = useState<PaperRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      const result = await fetchJson<PaperRow[]>(
        `/api/spaces/${encodeURIComponent(space)}/papers`,
      );
      setPapers(result || []);
      setLoading(false);
    }
    load();
  }, [space]);

  return (
    <List isLoading={loading} navigationTitle={`Papers — ${space}`} searchBarPlaceholder="Filter papers">
      <List.Item
        key="__none__"
        title="Let server decide (from URL)"
        subtitle="auto-resolve / auto-ingest"
        actions={
          <ActionPanel>
            <Action title="Pick" onAction={() => onPick(null)} />
          </ActionPanel>
        }
      />
      {papers.map((p) => (
        <List.Item
          key={p.paper_id}
          title={p.title}
          subtitle={p.type === "html" ? "html" : p.type}
          actions={
            <ActionPanel>
              <Action
                title="Ground Answers in This Paper"
                onAction={() => onPick({ paper_id: p.paper_id, title: p.title })}
              />
            </ActionPanel>
          }
        />
      ))}
    </List>
  );
}

// ── Composer ───────────────────────────────────────────────────────────────

interface ComposerProps {
  spaces: Space[];
  space: string;
  onSpaceChange: (space: string) => void;
  paperTitle: string | null;
  turns: Turn[];
  threadState: ThreadState;
  forceFresh: boolean;
  selectedText: string;
  source: Source;
  isLoading: boolean;
  onSubmit: (question: string) => void;
  onToggleForceFresh: () => void;
  onShowHistory: () => void;
  onRefreshSelection: () => void;
  onChangePaper: () => void;
  warning: string | null;
}

function Composer({
  spaces,
  space,
  onSpaceChange,
  paperTitle,
  turns,
  threadState,
  forceFresh,
  selectedText,
  source,
  isLoading,
  onSubmit,
  onToggleForceFresh,
  onShowHistory,
  onRefreshSelection,
  onChangePaper,
  warning,
}: ComposerProps) {
  const threadActive = turns.length > 0;

  async function handleSubmit(values: { question: string }) {
    if (!values.question.trim()) {
      await showToast({ style: Toast.Style.Failure, title: "Enter a question" });
      return;
    }
    await LocalStorage.setItem("paper-agent.lastSpace", space);
    onSubmit(values.question);
  }

  return (
    <Form
      isLoading={isLoading}
      actions={
        <ActionPanel>
          <Action.SubmitForm title={threadActive ? "Send" : "Ask"} onSubmit={handleSubmit} />
          <Action
            title={forceFresh ? "Undo Force New Thread" : "Force New Thread"}
            shortcut={{ modifiers: ["cmd"], key: "n" }}
            onAction={onToggleForceFresh}
          />
          {threadActive && (
            <Action
              title="View Full Thread"
              shortcut={{ modifiers: ["cmd"], key: "h" }}
              onAction={onShowHistory}
            />
          )}
          <Action
            title="Refresh Selection"
            shortcut={{ modifiers: ["cmd"], key: "r" }}
            onAction={onRefreshSelection}
          />
          <Action
            title="Change Paper…"
            shortcut={{ modifiers: ["shift", "cmd"], key: "p" }}
            onAction={onChangePaper}
          />
        </ActionPanel>
      }
    >
      {!threadActive ? (
        <Form.Dropdown id="space" title="Space" value={space} onChange={onSpaceChange}>
          {spaces.length > 0 ? (
            spaces.map((s) => (
              <Form.Dropdown.Item
                key={s.name}
                value={s.name}
                title={`${s.name} (${s.sessions} sessions)`}
              />
            ))
          ) : (
            <Form.Dropdown.Item
              value=""
              title={warning ?? "No spaces — create one with paper-agent init --space <name>"}
            />
          )}
        </Form.Dropdown>
      ) : (
        <Form.Description title="Space" text={space} />
      )}

      <Form.Description
        title="Paper"
        text={paperTitle ? `${paperTitle}\n${source.url || ""}`.trim() : source.url || "server decides (URL match / auto-ingest)"}
      />

      <Form.Description
        title="Thread"
        text={statusText(threadState, forceFresh, turns.length)}
      />

      {threadActive && (
        <Form.Description
          title={`History (last ${Math.min(turns.length, 5)} of ${turns.length})`}
          text={threadPreview(turns)}
        />
      )}

      {selectedText && (
        <Form.Description
          title={threadState.section && !forceFresh ? `Replying to §${threadState.section}` : "Replying to"}
          text={quoteText(selectedText)}
        />
      )}

      {warning && !threadActive && spaces.length > 0 && (
        <Form.Description title="Warning" text={warning} />
      )}

      <Form.TextArea
        id="question"
        title={forceFresh ? "New question" : threadActive ? "Reply" : "Question"}
        placeholder={
          selectedText
            ? "Reply to this section..."
            : threadState.state === "continuing" && !forceFresh
              ? "Continue the conversation..."
              : "What would you like to know?"
        }
        autoFocus
      />
    </Form>
  );
}

// ── Thread View (streaming transcript) ─────────────────────────────────────

interface ThreadViewProps {
  space: string;
  active: ActiveAsk | null;
  turns: Turn[];
  paperTitle: string;
  threadInfo: ThreadInfo | null;
  onPaperResolved: (paper: ResolvedPaper, space?: string) => void;
  onThreadInfo: (info: ThreadInfo) => void;
  onFinished: (answer: string) => void;
  onFollowUp: () => void;
  onForceFresh: () => void;
  onRefreshSelection: () => void;
  onChangePaper: () => void;
}

function ThreadView({
  space,
  active,
  turns,
  paperTitle,
  threadInfo,
  onPaperResolved,
  onThreadInfo,
  onFinished,
  onFollowUp,
  onForceFresh,
  onRefreshSelection,
  onChangePaper,
}: ThreadViewProps) {
  const [streamingAnswer, setStreamingAnswer] = useState("");
  const [banner, setBanner] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const sessionPathRef = useRef("");

  const streaming = active !== null;

  useEffect(() => {
    if (!active) return;

    const abort = new AbortController();
    let settled = false;
    let answer = "";

    setStreamingAnswer("");
    setBanner(null);
    setIsLoading(true);
    sessionPathRef.current = "";

    async function stream() {
      try {
        const res = await fetch(
          daemon(`/api/spaces/${encodeURIComponent(space)}/ask`),
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(active!.payload),
            signal: abort.signal,
          },
        );

        if (!res.ok) {
          const err = await res
            .json()
            .catch(() => ({ detail: `${res.status} ${res.statusText}` }));
          answer += `\n\n---\n**Error:** ${err.detail || "Request failed"}\n\nIs the daemon running? \`paper-agent serve\``;
          finish(false);
          return;
        }

        const reader = res.body?.getReader();
        if (!reader) {
          answer += "\n\n---\n**Error:** No response body received.";
          finish(false);
          return;
        }

        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
          const events = buffer.split("\n\n");
          buffer = events.pop() || "";

          for (const event of events) {
            const dataLines: string[] = [];
            for (const line of event.split("\n")) {
              if (line.startsWith("data: ")) dataLines.push(line.slice(6));
            }
            if (dataLines.length === 0) continue;
            const data = dataLines.join("\n");

            // Status events
            if (data.startsWith("{") && data.includes('"status"')) {
              try {
                const evt = JSON.parse(data);
                if (evt.status === "resolved") {
                  onPaperResolved(evt.paper, evt.space);
                  continue;
                }
                if (evt.status === "thread") {
                  onThreadInfo({ section: evt.section ?? "", continued: !!evt.continued });
                  continue;
                }
                if (evt.status === "ingesting") {
                  setBanner(evt.message || "Downloading and converting paper...");
                  continue;
                }
                if (evt.status === "ingested") {
                  setBanner(null);
                  continue;
                }
                if (evt.status === "ingest_failed") {
                  setBanner(`Ingestion failed — falling back to selected text (${evt.error})`);
                  continue;
                }
              } catch {
                // fall through
              }
            }

            if (data.startsWith("{") && data.includes("session_path")) {
              try {
                const meta = JSON.parse(data);
                if (meta.session_path) sessionPathRef.current = meta.session_path;
                continue;
              } catch {
                // fall through
              }
            }

            if (data === "[DONE]") continue;
            if (data === "[ERROR]") continue;

            if (!answer) setIsLoading(false);
            answer += data;
            setStreamingAnswer(answer);
          }
        }

        finish(true);
      } catch (err: unknown) {
        if (err instanceof Error && err.name === "AbortError") return;
        answer += `\n\n---\n**Error:** ${err instanceof Error ? err.message : "Unknown error"}`;
        finish(false);
      }
    }

    function finalizeText(): string {
      let text = answer.trim();
      if (sessionPathRef.current) {
        text += `\n\n---\n*Saved to vault*`;
      }
      return text;
    }

    function finish(ok: boolean) {
      if (settled) return;
      settled = true;
      const text = finalizeText();
      setStreamingAnswer(text);
      setIsLoading(false);
      onFinished(text);
      if (!ok) {
        showToast({
          style: Toast.Style.Failure,
          title: "Ask failed",
          message: "See the transcript for details",
        });
      }
    }

    stream();
    return () => abort.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active?.id]);

  const markdown = buildTranscript(
    space,
    paperTitle,
    turns,
    threadInfo,
    streaming ? active!.payload.question : null,
    streamingAnswer,
    banner,
  );

  const lastTurn = streaming ? null : turns.length > 0 ? turns[turns.length - 1] : null;

  return (
    <Detail
      markdown={markdown}
      isLoading={isLoading}
      navigationTitle={`${space}${paperTitle ? ` · ${paperTitle}` : ""}`}
      actions={
        <ActionPanel>
          {!streaming && (
            <Action title="Ask Follow-up" onAction={onFollowUp} />
          )}
          {lastTurn && (
            <Action.CopyToClipboard
              title="Copy Last Answer"
              content={lastTurn.answer}
              shortcut={{ modifiers: ["cmd"], key: "c" }}
            />
          )}
          <Action
            title="Refresh Selection"
            shortcut={{ modifiers: ["cmd"], key: "r" }}
            onAction={onRefreshSelection}
          />
          <Action
            title="Change Paper…"
            shortcut={{ modifiers: ["shift", "cmd"], key: "p" }}
            onAction={onChangePaper}
          />
          <Action
            title="Force New Thread"
            shortcut={{ modifiers: ["cmd"], key: "n" }}
            onAction={onForceFresh}
          />
        </ActionPanel>
      }
    />
  );
}

// ── Root ───────────────────────────────────────────────────────────────────

export default function Command(
  props: LaunchProps<{ launchContext?: AskLaunchContext }>,
) {
  const ctx = props.launchContext;
  const { push, pop } = useNavigation();

  const [spaces, setSpaces] = useState<Space[]>([]);
  const [space, setSpace] = useState("");
  const [resolvedPaper, setResolvedPaper] = useState<ResolvedPaper | null>(null);
  const [overridePaper, setOverridePaper] = useState<ResolvedPaper | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [active, setActive] = useState<ActiveAsk | null>(null);
  const [composing, setComposing] = useState(true);
  const [threadInfo, setThreadInfo] = useState<ThreadInfo | null>(null);
  const [threadState, setThreadState] = useState<ThreadState>(NO_PAPER_STATE);
  const [forceFresh, setForceFresh] = useState(false);
  const [selectedText, setSelectedText] = useState(ctx?.selectedText ?? "");
  const [source, setSource] = useState<Source>(ctx?.source ?? EMPTY_SOURCE);
  const [loading, setLoading] = useState(!ctx);
  const [warning, setWarning] = useState<string | null>(null);
  const askCounter = useRef(0);
  const lastHydratedUrl = useRef<string>("");

  // Space follows paper: resolve the captured URL (cross-space, no ingest),
  // switch to the owning space, hydrate the reading thread, and preview
  // whether the next ask would continue it or start fresh.
  async function hydrateFromUrl(url: string, selected: string, preferSpace: string) {
    lastHydratedUrl.current = url;
    if (!url) {
      setThreadState(NO_PAPER_STATE);
      return;
    }
    try {
      const res = await fetch(daemon("/api/resolve"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_url: url, selected_text: selected, space: preferSpace }),
      });
      if (!res.ok) return;
      const r = (await res.json()) as ResolvedThread;

      if (!r.found) {
        setTurns([]);
        setThreadState({ state: r.thread_state ?? "new_paper", section: "" });
        return;
      }

      if (r.space && r.paper_id) {
        setSpace(r.space);
        setResolvedPaper({ paper_id: r.paper_id, title: r.title ?? r.paper_id });
        setOverridePaper(null);
      }
      setThreadState({ state: r.thread_state ?? "fresh", section: r.section ?? "" });
      if ((r.qa_count ?? 0) > 0 && r.recent_qa && r.recent_qa.length > 0) {
        setTurns(r.recent_qa.map((qa) => ({ question: qa.question, answer: qa.answer })));
      } else {
        setTurns([]);
      }
    } catch {
      // daemon unreachable — composer falls back to defaults
    }
  }

  useEffect(() => {
    async function init() {
      let url = ctx?.source.url ?? "";
      let selected = ctx?.selectedText ?? "";
      if (!ctx) {
        setLoading(true);
        const captured = await captureContext();
        setSelectedText(captured.selectedText);
        setSource(captured.source);
        url = captured.source.url;
        selected = captured.selectedText;
      }

      const spacesResult = await fetchJson<Space[]>("/api/spaces");
      const spacesList: Space[] = spacesResult || [];
      if (!spacesResult) {
        setWarning("Daemon not reachable. Start it with: paper-agent serve");
      }

      const daemonCtx = await fetchJson<{ last_space: string | null }>("/api/context");
      const lsSpace = await LocalStorage.getItem<string>("paper-agent.lastSpace");

      let defSpace = "";
      if (daemonCtx?.last_space) defSpace = daemonCtx.last_space;
      else if (lsSpace) defSpace = lsSpace;
      else if (prefs().defaultSpace) defSpace = prefs().defaultSpace;
      else if (spacesList.length > 0) defSpace = spacesList[0].name;

      setSpaces(spacesList);
      setSpace(defSpace);
      await hydrateFromUrl(url, selected, defSpace);
      setLoading(false);
    }

    init();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function displayPaper(): string | null {
    if (overridePaper) return overridePaper.title;
    if (resolvedPaper) return resolvedPaper.title;
    return null;
  }

  function handleAsk(question: string) {
    const payload: AskPayload = {
      question,
      selected_text: selectedText,
      source_app: source.app,
      source_title: source.title,
      source_url: source.url,
      fresh: forceFresh,
    };
    if (overridePaper) payload.paper_id = overridePaper.paper_id;
    setThreadInfo(null);
    setComposing(false);
    askCounter.current += 1;
    setActive({ id: askCounter.current, payload });
  }

  function handleFinished(answer: string) {
    const q = active?.payload.question ?? "";
    setActive(null);
    setTurns((prev) => [...prev, { question: q, answer }]);
  }

  async function handleRefreshSelection() {
    try {
      const captured = await captureContext();
      setSelectedText(captured.selectedText);
      setSource(captured.source);
      if (captured.source.url) {
        // re-resolve even for the same URL: the new selection may flip
        // the thread state (continuing ↔ fresh)
        await hydrateFromUrl(captured.source.url, captured.selectedText, space);
      } else {
        setThreadState(NO_PAPER_STATE);
      }
      await showToast({ style: Toast.Style.Success, title: "Selection refreshed" });
    } catch {
      await showToast({ style: Toast.Style.Failure, title: "Failed to capture selection" });
    }
  }

  function handleToggleForceFresh() {
    const next = !forceFresh;
    setForceFresh(next);
    if (next) {
      // forced fresh: clear the displayed thread, land in composer
      setTurns([]);
      setActive(null);
      setThreadInfo(null);
      setThreadState((prev) => ({ ...prev, state: "fresh" }));
      setComposing(true);
    } else if (source.url) {
      // undo: re-hydrate from the vault
      hydrateFromUrl(source.url, selectedText, space);
    }
  }

  function handleChangePaper() {
    if (!space) return;
    push(
      <PaperPicker
        space={space}
        onPick={(p) => {
          setOverridePaper(p);
          pop();
        }}
      />,
    );
  }

  const inThread = !composing && (active !== null || turns.length > 0);

  return inThread ? (
    <ThreadView
      space={space}
      active={active}
      turns={turns}
      paperTitle={(overridePaper ?? resolvedPaper)?.title ?? ""}
      threadInfo={threadInfo}
      onPaperResolved={(paper, resolvedSpace) => {
        setResolvedPaper(paper);
        if (resolvedSpace) setSpace(resolvedSpace);
      }}
      onThreadInfo={setThreadInfo}
      onFinished={handleFinished}
      onFollowUp={() => setComposing(true)}
      onForceFresh={handleToggleForceFresh}
      onRefreshSelection={handleRefreshSelection}
      onChangePaper={handleChangePaper}
    />
  ) : (
    <Composer
      spaces={spaces}
      space={space}
      onSpaceChange={setSpace}
      paperTitle={displayPaper()}
      turns={turns}
      threadState={threadState}
      forceFresh={forceFresh}
      selectedText={selectedText}
      source={source}
      isLoading={loading}
      onSubmit={handleAsk}
      onToggleForceFresh={handleToggleForceFresh}
      onShowHistory={() => setComposing(false)}
      onRefreshSelection={handleRefreshSelection}
      onChangePaper={handleChangePaper}
      warning={warning}
    />
  );
}
