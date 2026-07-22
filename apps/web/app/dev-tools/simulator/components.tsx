"use client";

import type { TraceRecord } from "@lead-recovery/shared";

const panelStyle: React.CSSProperties = {
  background: "#131a2e",
  border: "1px solid #232d46",
  borderRadius: 8,
  padding: 16,
  marginBottom: 16,
};

const headingStyle: React.CSSProperties = {
  fontSize: 14,
  fontWeight: 600,
  color: "#9fb0c9",
  textTransform: "uppercase",
  letterSpacing: 0.5,
  marginBottom: 10,
};

export function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={panelStyle}>
      <div style={headingStyle}>{title}</div>
      {children}
    </div>
  );
}

export function Badge({ text, tone = "neutral" }: { text: string; tone?: string }) {
  const colors: Record<string, [string, string]> = {
    ok: ["#123a24", "#5fd48a"],
    completed: ["#123a24", "#5fd48a"],
    error: ["#3a1414", "#f26b6b"],
    failed: ["#3a1414", "#f26b6b"],
    running: ["#1e2e4a", "#7aa6ff"],
    queued: ["#2a2440", "#c39bff"],
    waiting_on_reply: ["#3a2e14", "#f2b96b"],
    neutral: ["#1b2338", "#9fb0c9"],
  };
  const [bg, fg] = colors[tone] ?? colors.neutral;
  return (
    <span
      style={{
        background: bg,
        color: fg,
        borderRadius: 4,
        padding: "2px 8px",
        fontSize: 12,
        fontWeight: 600,
      }}
    >
      {text}
    </span>
  );
}

export function JsonBlock({ data }: { data: unknown }) {
  return (
    <pre
      style={{
        background: "#0b1020",
        border: "1px solid #232d46",
        borderRadius: 6,
        padding: 10,
        fontSize: 12,
        overflowX: "auto",
        color: "#cdd8ea",
        margin: 0,
      }}
    >
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}

function Expandable({ label, data }: { label: string; data: unknown }) {
  return (
    <details style={{ marginBottom: 6 }}>
      <summary style={{ cursor: "pointer", fontSize: 13, color: "#cdd8ea" }}>{label}</summary>
      <div style={{ marginTop: 6 }}>
        <JsonBlock data={data} />
      </div>
    </details>
  );
}

export function Timeline({ records }: { records: TraceRecord[] }) {
  if (!records.length) return <Empty text="No timeline yet — run a simulation." />;
  return (
    <div>
      {records.map((r, i) => (
        <div key={r.seq} style={{ display: "flex", gap: 10, fontSize: 13, marginBottom: 6 }}>
          <span style={{ color: "#6f7f99", minWidth: 90 }}>
            {new Date(r.ts as string).toLocaleTimeString()}
          </span>
          <span style={{ color: "#5a8fd6" }}>{String(r.timeline_kind)}</span>
          <span style={{ color: "#e7ecf5" }}>{String(r.label)}</span>
          {i < records.length - 1 && <span style={{ color: "#3a4666" }}> ↓</span>}
        </div>
      ))}
    </div>
  );
}

export function WorkflowInspector({ steps }: { steps: TraceRecord[] }) {
  if (!steps.length) return <Empty text="No workflow steps executed yet." />;
  const current = steps[steps.length - 1];
  return (
    <div>
      {steps.map((s, i) => {
        const isCurrent = s === current;
        return (
          <div key={s.seq}>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "6px 8px",
                borderRadius: 6,
                background: isCurrent ? "#1e2e4a" : "transparent",
                marginBottom: 2,
              }}
            >
              <span style={{ fontWeight: isCurrent ? 700 : 400 }}>{String(s.step)}</span>
              <Badge
                text={String(s.outcome)}
                tone={String(s.outcome).toLowerCase() === "pause" ? "waiting_on_reply" : "ok"}
              />
            </div>
            <Expandable label="state at this step" data={s.state} />
            {i < steps.length - 1 && (
              <div style={{ textAlign: "center", color: "#3a4666" }}>↓</div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function EventBusInspector({
  events,
  subscribers,
}: {
  events: TraceRecord[];
  subscribers: TraceRecord[];
}) {
  if (!events.length) return <Empty text="No events published yet." />;
  return (
    <div>
      {events.map((e) => {
        const subs = subscribers.filter((s) => s.event_type === e.event_type);
        return (
          <div key={e.seq} style={{ marginBottom: 12 }}>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <strong>{String(e.event_type)}</strong>
              <span style={{ fontSize: 12, color: "#6f7f99" }}>
                {new Date(e.ts as string).toLocaleTimeString()} · {String(e.subscriber_count)}{" "}
                subscriber(s)
              </span>
            </div>
            {subs.map((s) => (
              <div key={s.seq} style={{ fontSize: 12, color: "#9fb0c9", marginLeft: 12 }}>
                <Badge text={String(s.status)} tone={String(s.status)} /> {String(s.handler)} —{" "}
                {String(s.duration_ms)}ms {s.error ? `(${String(s.error)})` : ""}
              </div>
            ))}
            <Expandable label="payload" data={e.payload} />
          </div>
        );
      })}
    </div>
  );
}

export function QueueInspector({ jobs }: { jobs: TraceRecord[] }) {
  if (!jobs.length) return <Empty text="No queued jobs yet." />;
  return (
    <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
      <thead>
        <tr style={{ color: "#6f7f99", textAlign: "left" }}>
          <th style={{ padding: 4 }}>Task</th>
          <th>Status</th>
          <th>Duration</th>
          <th>Retries</th>
        </tr>
      </thead>
      <tbody>
        {jobs.map((j) => (
          <tr key={j.seq} style={{ borderTop: "1px solid #232d46" }}>
            <td style={{ padding: 4 }}>{String(j.task_name)}()</td>
            <td>
              <Badge text={String(j.status)} tone={String(j.status)} />
            </td>
            <td>{j.duration_ms != null ? `${String(j.duration_ms)}ms` : "—"}</td>
            <td>{String(j.retries ?? 0)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function AIExtractionViewer({ calls }: { calls: TraceRecord[] }) {
  if (!calls.length) return <Empty text="No AI extraction calls yet." />;
  return (
    <div>
      {calls.map((c) => (
        <div key={c.seq} style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 12, color: "#6f7f99", marginBottom: 4 }}>
            model: {String(c.model)} · prompt {String(c.prompt_version)} · schema{" "}
            {String(c.schema_version)}
          </div>
          <Expandable label="Prompt sent to OpenAI" data={c.prompt} />
          <Expandable label="Organization context" data={c.organization_context} />
          <Expandable label="Conversation input" data={c.input} />
          <Expandable label="Raw response" data={c.raw_response} />
          <Expandable label="Validated model" data={c.validated_model} />
          <Expandable label="Missing fields" data={c.missing_fields} />
        </div>
      ))}
    </div>
  );
}

export function DbChangesInspector({ changes }: { changes: TraceRecord[] }) {
  if (!changes.length) return <Empty text="No database changes recorded yet." />;
  return (
    <div>
      {changes.map((c) => (
        <div key={c.seq} style={{ marginBottom: 8 }}>
          <div style={{ fontSize: 13 }}>
            <Badge
              text={String(c.operation)}
              tone={c.operation === "insert" ? "ok" : c.operation === "delete" ? "error" : "running"}
            />{" "}
            <strong>{String(c.table)}</strong>{" "}
            <span style={{ color: "#6f7f99" }}>#{String(c.pk)}</span>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            {c.before != null && <Expandable label="before" data={c.before} />}
            {c.after != null && <Expandable label="after" data={c.after} />}
          </div>
        </div>
      ))}
    </div>
  );
}

export function ApiInspector({
  calls,
}: {
  calls: {
    method: string;
    route: string;
    status: number;
    latency_ms: number;
    request_body?: unknown;
    response_body?: unknown;
    timestamp: string;
  }[];
}) {
  if (!calls.length) return <Empty text="No API calls made yet." />;
  return (
    <div>
      {calls
        .slice()
        .reverse()
        .map((c, i) => (
          <div key={i} style={{ marginBottom: 8, fontSize: 13 }}>
            <span style={{ color: "#5a8fd6", fontWeight: 600 }}>{c.method}</span>{" "}
            <span>{c.route}</span>{" "}
            <Badge text={String(c.status)} tone={c.status < 400 ? "ok" : "error"} />{" "}
            <span style={{ color: "#6f7f99" }}>{c.latency_ms}ms</span>
            <Expandable label="request/response" data={{ request: c.request_body, response: c.response_body }} />
          </div>
        ))}
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <div style={{ color: "#6f7f99", fontSize: 13, fontStyle: "italic" }}>{text}</div>;
}
