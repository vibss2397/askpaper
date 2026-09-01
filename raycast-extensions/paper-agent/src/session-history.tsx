import {
  List,
  ActionPanel,
  Action,
  Detail,
  useNavigation,
  getPreferenceValues,
  showToast,
  Toast,
} from "@raycast/api";
import { useState, useEffect } from "react";

// ── Types ──────────────────────────────────────────────────────────────────

interface Preferences {
  daemonUrl: string;
  defaultSpace: string;
}

interface SessionMeta {
  file: string;
  path: string;
  qa_count: number;
  modified: number;
  slug: string;
  date: string;
}

interface QAPair {
  id: string;
  question: string;
  answer: string;
  context: string;
  source: string;
  file: string;
}

interface Space {
  name: string;
  sessions: number;
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

function formatDate(iso: string): string {
  if (!iso) return "ongoing";
  const d = new Date(iso + "T00:00:00");
  if (isNaN(d.getTime())) return "ongoing";
  return d.toLocaleDateString(undefined, {
    weekday: "short",
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

// ── Session Detail View ────────────────────────────────────────────────────

function SessionDetail({ space, meta }: { space: string; meta: SessionMeta }) {
  const [qaPairs, setQaPairs] = useState<QAPair[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      const endpoint = meta.date
        ? `/api/spaces/${encodeURIComponent(space)}/sessions/${meta.date}`
        : `/api/spaces/${encodeURIComponent(space)}/session-files/${encodeURIComponent(meta.file)}`;
      const data = await fetchJson<QAPair[]>(endpoint);
      if (data) {
        setQaPairs(data);
      }
      setLoading(false);
    }
    load();
  }, [space, meta.date, meta.file]);

  if (loading) {
    return <Detail isLoading />;
  }

  const heading = meta.date ? `Session — ${formatDate(meta.date)}` : `Reading — ${meta.slug}`;

  const markdown = qaPairs
    .map(
      (qa) =>
        `### ${qa.id}\n\n**Q:** ${qa.question}\n\n${
          qa.context ? `> ${qa.context.replace(/\n/g, "\n> ")}\n\n` : ""
        }${qa.source ? `*Source: ${qa.source}*\n\n` : ""}**A:** ${qa.answer}\n\n---\n`,
    )
    .join("\n");

  return (
    <Detail
      markdown={`# ${heading}\n\n${markdown || "*No Q&A found for this session.*"}`}
      navigationTitle={`${space} — ${meta.date ? formatDate(meta.date) : meta.slug}`}
    />
  );
}

// ── Session List ───────────────────────────────────────────────────────────

function SessionList({ space }: { space: string }) {
  const { push } = useNavigation();
  const [sessions, setSessions] = useState<SessionMeta[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      const data = await fetchJson<SessionMeta[]>(
        `/api/spaces/${encodeURIComponent(space)}/sessions`,
      );
      if (data) {
        setSessions(data);
      }
      setLoading(false);
    }
    load();
  }, [space]);

  return (
    <List
      isLoading={loading}
      navigationTitle={`${space} — Sessions`}
      searchBarPlaceholder="Search sessions..."
    >
      {sessions.map((s) => (
        <List.Item
          key={s.path}
          title={s.date ? s.slug : `${s.slug} (reading)`}
          subtitle={`${formatDate(s.date)} — ${s.qa_count} Q&As`}
          accessories={[
            {
              text: new Date(s.modified * 1000).toLocaleTimeString(undefined, {
                hour: "2-digit",
                minute: "2-digit",
              }),
            },
          ]}
          actions={
            <ActionPanel>
              <Action
                title="View Session"
                onAction={() =>
                  push(<SessionDetail space={space} meta={s} />)
                }
              />
            </ActionPanel>
          }
        />
      ))}
      {sessions.length === 0 && !loading && (
        <List.EmptyView
          title="No sessions found"
          description={`No Q&A sessions in "${space}". Use "Ask Paper Agent" to start one.`}
        />
      )}
    </List>
  );
}

// ── Space Selector ─────────────────────────────────────────────────────────

export default function Command() {
  const { push } = useNavigation();
  const [spaces, setSpaces] = useState<Space[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      const data = await fetchJson<Space[]>("/api/spaces");
      if (!data) {
        setError("Daemon not reachable. Start it with: paper-agent serve");
        await showToast({
          style: Toast.Style.Failure,
          title: "Daemon not reachable",
        });
      } else {
        setSpaces(data);
      }
      setLoading(false);
    }
    load();
  }, []);

  return (
    <List
      isLoading={loading}
      navigationTitle="Paper Agent — Sessions"
      searchBarPlaceholder="Select a space..."
    >
      {spaces.map((s) => (
        <List.Item
          key={s.name}
          title={s.name}
          subtitle={`${s.sessions} sessions`}
          actions={
            <ActionPanel>
              <Action
                title="View Sessions"
                onAction={() => push(<SessionList space={s.name} />)}
              />
            </ActionPanel>
          }
        />
      ))}
      {spaces.length === 0 && !loading && (
        <List.EmptyView
          title={error || "No spaces found"}
          description="Create a space with: paper-agent init --space <name>"
        />
      )}
    </List>
  );
}
