import {
  Form,
  ActionPanel,
  Action,
  Detail,
  useNavigation,
  getPreferenceValues,
  LocalStorage,
  showToast,
  Toast,
} from "@raycast/api";
import { useState, useEffect } from "react";

// ── Types ──────────────────────────────────────────────────────────────────

interface Preferences {
  daemonUrl: string;
  defaultSpace: string;
}

interface Space {
  name: string;
  sessions: number;
}

interface Paper {
  paper_id: string;
  title: string;
  type: string;
  source_url: string;
  page_count: number | null;
}

interface Context {
  last_space: string | null;
  last_source_url: string | null;
  last_source_title: string | null;
  last_source_app: string | null;
  active_paper_id: string | null;
  last_session_file: string | null;
}

interface SummarizeResponse {
  status: "ok" | "skipped";
  summary_path?: string;
  markdown?: string;
  themes?: number;
  open_threads?: number;
  gaps?: number;
  reason?: string;
}

interface SynthesizeResponse {
  status: "ok" | "skipped";
  insights_path?: string;
  markdown?: string;
  connections?: number;
  reason?: string;
}

interface KnowledgeResponse {
  status: "ok" | "skipped";
  knowledge_path?: string;
  markdown?: string;
  themes?: number;
  key_facts?: number;
  reason?: string;
}

interface OpenQuestionsResponse {
  status: "ok" | "skipped";
  questions_path?: string;
  markdown?: string;
  questions?: number;
  reason?: string;
}

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

// ── Knowledge Result View ──────────────────────────────────────────────────

function KnowledgeView({ space }: { space: string }) {
  const { push } = useNavigation();
  const [markdown, setMarkdown] = useState("# Building knowledge...\n\n");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function generate() {
      try {
        const res = await fetch(
          daemon(`/api/spaces/${encodeURIComponent(space)}/knowledge`),
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
          },
        );

        const data: KnowledgeResponse = await res.json();

        if (!res.ok) {
          setMarkdown(
            `# Error\n\n**${res.status}:** ${(data as unknown as { detail?: string }).detail || "Request failed"}\n\nIs the daemon running? Run \`paper-agent serve\`.`,
          );
          setIsLoading(false);
          return;
        }

        if (data.status === "skipped") {
          setMarkdown(
            `# No Knowledge Generated\n\n${data.reason || "No summarized papers found. Summarize papers first."}`,
          );
          setIsLoading(false);
          return;
        }

        setMarkdown(data.markdown || "# Knowledge generated");
        setIsLoading(false);
        await showToast({
          style: Toast.Style.Success,
          title: `Knowledge written (${data.themes} themes, ${data.key_facts} facts)`,
        });
      } catch (err) {
        setMarkdown(
          `# Error\n\n${err instanceof Error ? err.message : "Unknown error"}\n\nIs the daemon running?`,
        );
        setIsLoading(false);
      }
    }

    generate();
  }, [space]);

  return (
    <Detail
      markdown={markdown}
      isLoading={isLoading}
      navigationTitle={`Knowledge — ${space}`}
      actions={
        <ActionPanel>
          <Action
            title="Open Questions"
            onAction={() => push(<OpenQuestionsView space={space} />)}
            shortcut={{ modifiers: ["cmd"], key: "o" }}
          />
        </ActionPanel>
      }
    />
  );
}

// ── Open Questions Result View ─────────────────────────────────────────────

function OpenQuestionsView({ space }: { space: string }) {
  const [markdown, setMarkdown] = useState("# Curating open questions...\n\n");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function generate() {
      try {
        const res = await fetch(
          daemon(`/api/spaces/${encodeURIComponent(space)}/open-questions`),
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
          },
        );

        const data: OpenQuestionsResponse = await res.json();

        if (!res.ok) {
          setMarkdown(
            `# Error\n\n**${res.status}:** ${(data as unknown as { detail?: string }).detail || "Request failed"}\n\nIs the daemon running? Run \`paper-agent serve\`.`,
          );
          setIsLoading(false);
          return;
        }

        if (data.status === "skipped") {
          setMarkdown(
            `# No Open Questions\n\n${data.reason || "No open questions or gaps found. All threads resolved."}`,
          );
          setIsLoading(false);
          return;
        }

        setMarkdown(data.markdown || "# Open questions generated");
        setIsLoading(false);
        await showToast({
          style: Toast.Style.Success,
          title: `Open questions written (${data.questions} questions)`,
        });
      } catch (err) {
        setMarkdown(
          `# Error\n\n${err instanceof Error ? err.message : "Unknown error"}\n\nIs the daemon running?`,
        );
        setIsLoading(false);
      }
    }

    generate();
  }, [space]);

  return (
    <Detail
      markdown={markdown}
      isLoading={isLoading}
      navigationTitle={`Open Questions — ${space}`}
    />
  );
}

// ── Synthesis Result View ──────────────────────────────────────────────────

function SynthesisView({ space }: { space: string }) {
  const { push } = useNavigation();
  const [markdown, setMarkdown] = useState("# Synthesizing...\n\n");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function generate() {
      try {
        const res = await fetch(
          daemon(`/api/spaces/${encodeURIComponent(space)}/synthesize`),
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
          },
        );

        const data: SynthesizeResponse = await res.json();

        if (!res.ok) {
          setMarkdown(
            `# Error\n\n**${res.status}:** ${(data as unknown as { detail?: string }).detail || "Request failed"}\n\nIs the daemon running? Run \`paper-agent serve\`.`,
          );
          setIsLoading(false);
          return;
        }

        if (data.status === "skipped") {
          setMarkdown(
            `# No Connections Found\n\n${data.reason || "No cross-paper connections found."}\n\nYou need at least 2 papers with summaries to synthesize.`,
          );
          setIsLoading(false);
          return;
        }

        setMarkdown(data.markdown || "# Synthesis generated");
        setIsLoading(false);
        await showToast({
          style: Toast.Style.Success,
          title: `Synthesis written (${data.connections} connections)`,
        });
      } catch (err) {
        setMarkdown(
          `# Error\n\n${err instanceof Error ? err.message : "Unknown error"}\n\nIs the daemon running?`,
        );
        setIsLoading(false);
      }
    }

    generate();
  }, [space]);

  return (
    <Detail
      markdown={markdown}
      isLoading={isLoading}
      navigationTitle={`Synthesize — ${space}`}
      actions={
        <ActionPanel>
          <Action
            title="Update Knowledge"
            onAction={() => push(<KnowledgeView space={space} />)}
            shortcut={{ modifiers: ["cmd"], key: "k" }}
          />
          <Action
            title="Open Questions"
            onAction={() => push(<OpenQuestionsView space={space} />)}
            shortcut={{ modifiers: ["cmd"], key: "o" }}
          />
        </ActionPanel>
      }
    />
  );
}

// ── Summary Result View ────────────────────────────────────────────────────

function SummaryView({
  space,
  paperId,
  paperTitle,
}: {
  space: string;
  paperId: string;
  paperTitle: string;
}) {
  const { push } = useNavigation();
  const [markdown, setMarkdown] = useState("# Generating summary...\n\n");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function generate() {
      try {
        const res = await fetch(
          daemon(`/api/spaces/${encodeURIComponent(space)}/summarize`),
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ paper_id: paperId }),
          },
        );

        const data: SummarizeResponse = await res.json();

        if (!res.ok) {
          setMarkdown(
            `# Error\n\n**${res.status}:** ${(data as unknown as { detail?: string }).detail || "Request failed"}\n\nIs the daemon running? Run \`paper-agent serve\`.`,
          );
          setIsLoading(false);
          return;
        }

        if (data.status === "skipped") {
          setMarkdown(
            `# No Summary Generated\n\n${data.reason || "Q&A was too superficial to summarize."}\n\nAsk more questions about this paper first, then try again.`,
          );
          setIsLoading(false);
          return;
        }

        setMarkdown(data.markdown || "# Summary generated");
        setIsLoading(false);
        await showToast({
          style: Toast.Style.Success,
          title: `Summary written (${data.themes} themes)`,
        });
      } catch (err) {
        setMarkdown(
          `# Error\n\n${err instanceof Error ? err.message : "Unknown error"}\n\nIs the daemon running?`,
        );
        setIsLoading(false);
      }
    }

    generate();
  }, [space, paperId]);

  return (
    <Detail
      markdown={markdown}
      isLoading={isLoading}
      navigationTitle={`End Paper — ${paperTitle}`}
      actions={
        <ActionPanel>
          <Action
            title="Synthesize Space"
            onAction={() => push(<SynthesisView space={space} />)}
            shortcut={{ modifiers: ["cmd"], key: "s" }}
          />
          <Action
            title="Update Knowledge"
            onAction={() => push(<KnowledgeView space={space} />)}
            shortcut={{ modifiers: ["cmd"], key: "k" }}
          />
          <Action
            title="Open Questions"
            onAction={() => push(<OpenQuestionsView space={space} />)}
            shortcut={{ modifiers: ["cmd"], key: "o" }}
          />
        </ActionPanel>
      }
    />
  );
}

// ── End Paper Form ─────────────────────────────────────────────────────────

const LS_LAST_SPACE = "paper-agent.lastSpace";
const LS_LAST_PAPER = "paper-agent.lastPaper";

export default function Command() {
  const { push } = useNavigation();

  const [spaces, setSpaces] = useState<Space[]>([]);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [defaultSpace, setDefaultSpace] = useState("");
  const [defaultPaper, setDefaultPaper] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedSpace, setSelectedSpace] = useState("");

  useEffect(() => {
    async function init() {
      const spacesResult = await fetchJson<Space[]>("/api/spaces");
      let spacesList: Space[] = spacesResult || [];
      if (!spacesResult) {
        setError("Daemon not reachable. Start it with: paper-agent serve");
      }

      const daemonCtx = await fetchJson<Context>("/api/context");
      const lsSpace = await LocalStorage.getItem<string>(LS_LAST_SPACE);

      let defSpace = "";
      if (daemonCtx?.last_space) {
        defSpace = daemonCtx.last_space;
      } else if (lsSpace) {
        defSpace = lsSpace;
      } else if (prefs().defaultSpace) {
        defSpace = prefs().defaultSpace;
      } else if (spacesList.length > 0) {
        defSpace = spacesList[0].name;
      }

      setSpaces(spacesList);
      setDefaultSpace(defSpace);
      setSelectedSpace(defSpace);
      setLoading(false);

      if (defSpace) {
        await loadPapers(defSpace, daemonCtx?.active_paper_id);
      }
    }

    init();
  }, []);

  async function loadPapers(spaceName: string, activePaperId?: string | null) {
    const papersResult = await fetchJson<Paper[]>(
      `/api/spaces/${encodeURIComponent(spaceName)}/papers`,
    );
    const papersList: Paper[] = papersResult || [];
    setPapers(papersList);

    let defPaper = "";
    if (activePaperId && papersList.some((p) => p.paper_id === activePaperId)) {
      defPaper = activePaperId;
    } else {
      const lsPaper = await LocalStorage.getItem<string>(
        `${LS_LAST_PAPER}.${spaceName}`,
      );
      if (lsPaper && papersList.some((p) => p.paper_id === lsPaper)) {
        defPaper = lsPaper;
      } else if (papersList.length > 0) {
        defPaper = papersList[0].paper_id;
      }
    }
    setDefaultPaper(defPaper);
  }

  async function handleSpaceChange(newValue: string) {
    setSelectedSpace(newValue);
    await loadPapers(newValue);
  }

  async function handleSubmit(values: { space: string; paper: string }) {
    if (!values.paper) {
      await showToast({
        style: Toast.Style.Failure,
        title: "Select a paper",
      });
      return;
    }

    await LocalStorage.setItem(LS_LAST_SPACE, values.space);
    await LocalStorage.setItem(
      `${LS_LAST_PAPER}.${values.space}`,
      values.paper,
    );

    const paper = papers.find((p) => p.paper_id === values.paper);
    const paperTitle = paper?.title || values.paper;

    push(
      <SummaryView
        space={values.space}
        paperId={values.paper}
        paperTitle={paperTitle}
      />,
    );
  }

  return (
    <Form
      isLoading={loading}
      actions={
        <ActionPanel>
          <Action.SubmitForm title="End Paper" onSubmit={handleSubmit} />
        </ActionPanel>
      }
    >
      <Form.Description
        title="End Paper"
        text="Generate a Q&A insight summary for a paper you've finished reading. Requires at least 5 Q&A sessions."
      />

      <Form.Dropdown
        id="space"
        title="Space"
        defaultValue={defaultSpace}
        storeValue
        onChange={handleSpaceChange}
      >
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
            title={
              error
                ? "Daemon not reachable"
                : "No spaces — create one with paper-agent init --space <name>"
            }
          />
        )}
      </Form.Dropdown>

      {papers.length > 0 ? (
        <Form.Dropdown
          id="paper"
          title="Paper"
          defaultValue={defaultPaper}
          storeValue
        >
          {papers.map((p) => (
            <Form.Dropdown.Item
              key={p.paper_id}
              value={p.paper_id}
              title={p.title}
            />
          ))}
        </Form.Dropdown>
      ) : (
        <Form.Description
          title="No papers"
          text={selectedSpace ? `No papers in "${selectedSpace}". Ingest one first.` : "Select a space first."}
        />
      )}

      {error && <Form.Description title="Warning" text={error} />}
    </Form>
  );
}
