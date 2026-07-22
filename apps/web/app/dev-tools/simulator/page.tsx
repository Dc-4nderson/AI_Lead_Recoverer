"use client";

import { useEffect, useState } from "react";
import type {
  Organization,
  SimulationRunRequest,
  SimulationRunResponse,
  SimulatorScenario,
  WorkflowInfo,
} from "@lead-recovery/shared";
import { api, clearApiCallLog, getApiCallLog } from "../../../lib/api-client";
import {
  AIExtractionViewer,
  ApiInspector,
  Badge,
  DbChangesInspector,
  EventBusInspector,
  JsonBlock,
  Panel,
  QueueInspector,
  Timeline,
  WorkflowInspector,
} from "./components";

// Preset scenarios (§ Scenario Builder). Loading a preset just fills the same
// SimulationRunRequest the "Run" button sends — no special-cased logic.
const PRESETS: Record<string, SimulationRunRequest> = {
  "Missed Call (no reply)": {
    workflow: "missed_call_recovery",
    caller_number: "+15551230000",
    business_number: "+15559990000",
    conversation_turns: [],
    use_real_ai: false,
  },
  "Emergency Plumbing": {
    workflow: "missed_call_recovery",
    caller_number: "+15551230001",
    business_number: "+15559990000",
    conversation_turns: ["I need emergency plumbing at 123 Main St, ASAP, my basement is flooding"],
    use_real_ai: false,
  },
  "Spam Caller": {
    workflow: "missed_call_recovery",
    caller_number: "+15551230002",
    business_number: "+15559990000",
    conversation_turns: ["You've won free money! Click here for your crypto prize"],
    use_real_ai: false,
  },
  "Existing Customer": {
    workflow: "missed_call_recovery",
    caller_number: "+15551230003",
    business_number: "+15559990000",
    conversation_turns: ["Hi, I'm an existing customer, you serviced my AC last time at 456 Oak Ave"],
    use_real_ai: false,
  },
  "New Lead — HVAC Appointment": {
    workflow: "missed_call_recovery",
    caller_number: "+15551230004",
    business_number: "+15559990000",
    conversation_turns: [
      "My AC stopped working at 789 Pine St",
      "Can we schedule an appointment for tomorrow?",
    ],
    use_real_ai: false,
  },
};

const emptyRequest: SimulationRunRequest = PRESETS["Missed Call (no reply)"];

export default function SimulatorPage() {
  const [orgId, setOrgId] = useState("");
  const [token, setToken] = useState("");

  useEffect(() => {
    setOrgId(localStorage.getItem("sim_org_id") ?? "");
    setToken(localStorage.getItem("sim_token") ?? "");
  }, []);
  useEffect(() => {
    localStorage.setItem("sim_org_id", orgId);
  }, [orgId]);
  useEffect(() => {
    localStorage.setItem("sim_token", token);
  }, [token]);

  const [myOrgs, setMyOrgs] = useState<Organization[]>([]);
  const [workflows, setWorkflows] = useState<WorkflowInfo[]>([]);
  const [scenarios, setScenarios] = useState<SimulatorScenario[]>([]);
  const [req, setReq] = useState<SimulationRunRequest>(emptyRequest);
  const [newTurn, setNewTurn] = useState("");
  const [overridesText, setOverridesText] = useState("{}");
  const [result, setResult] = useState<SimulationRunResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [apiCalls, setApiCalls] = useState(getApiCallLog());

  const connected = Boolean(orgId && token);

  async function lookupMyOrgs() {
    if (!token) return;
    try {
      const orgs = await api.listMyOrganizations(token);
      setMyOrgs(orgs);
      if (!orgId && orgs.length) setOrgId(orgs[0].id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setApiCalls([...getApiCallLog()]);
    }
  }

  async function refreshMeta() {
    if (!connected) return;
    try {
      const [wf, sc] = await Promise.all([
        api.simulator.listWorkflows(orgId, token),
        api.simulator.listScenarios(orgId, token),
      ]);
      setWorkflows(wf);
      setScenarios(sc);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setApiCalls([...getApiCallLog()]);
    }
  }

  useEffect(() => {
    refreshMeta();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId, token]);

  function updateReq<K extends keyof SimulationRunRequest>(key: K, value: SimulationRunRequest[K]) {
    setReq((r) => ({ ...r, [key]: value }));
  }

  async function runSimulation() {
    setBusy(true);
    setError(null);
    try {
      let overrides: Record<string, unknown> | null = null;
      if (overridesText.trim()) {
        overrides = JSON.parse(overridesText);
      }
      const out = await api.simulator.run(orgId, token, {
        ...req,
        business_settings_overrides: overrides,
      });
      setResult(out);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      setApiCalls([...getApiCallLog()]);
    }
  }

  async function stepForward() {
    if (!result?.workflow_run?.id) return;
    setBusy(true);
    setError(null);
    try {
      const url = `/organizations/${orgId}/simulator/step`;
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}/api/v1${url}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
          body: JSON.stringify({ workflow_run_id: result.workflow_run.id, use_real_ai: req.use_real_ai }),
        }
      );
      const body = await res.json();
      if (!res.ok) throw new Error(body?.error?.message ?? "step failed");
      // Merge the new step's trace onto the existing one for a continuous view.
      setResult((prev) =>
        prev
          ? {
              ...body,
              trace: mergeTrace(prev.trace, body.trace),
            }
          : body
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function replayEvent(eventType: string, payload: Record<string, unknown>) {
    setBusy(true);
    setError(null);
    try {
      const out = await api.simulator.replayEvent(orgId, token, eventType, payload);
      setResult((prev) =>
        prev ? { ...prev, trace: mergeTrace(prev.trace, out.trace) } : (out as unknown as SimulationRunResponse)
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      setApiCalls([...getApiCallLog()]);
    }
  }

  async function resetConversation() {
    if (!result?.conversation_id) return;
    setBusy(true);
    setError(null);
    try {
      await api.simulator.reset(orgId, token, result.conversation_id);
      setResult(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      setApiCalls([...getApiCallLog()]);
    }
  }

  function restart() {
    setResult(null);
    setError(null);
    clearApiCallLog();
    setApiCalls([]);
  }

  async function saveScenario() {
    const name = prompt("Scenario name?");
    if (!name) return;
    try {
      await api.simulator.saveScenario(orgId, token, name, req);
      refreshMeta();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  function loadScenario(s: SimulatorScenario) {
    setReq(s.payload);
    setOverridesText(JSON.stringify(s.payload.business_settings_overrides ?? {}, null, 2));
  }

  async function deleteScenario(id: string) {
    await api.simulator.deleteScenario(orgId, token, id);
    refreshMeta();
  }

  return (
    <main style={{ maxWidth: 1200, margin: "0 auto", padding: "32px 24px", fontSize: 14 }}>
      <div style={{ color: "#6f7f99", fontSize: 13, marginBottom: 4 }}>
        Developer Tools / Workflow Simulator
      </div>
      <h1 style={{ fontSize: 26, marginTop: 0, marginBottom: 4 }}>Workflow Simulator</h1>
      <p style={{ color: "#9fb0c9", marginTop: 0, marginBottom: 20, maxWidth: 700 }}>
        Exercises the exact production backend — real event bus, real workflow engine, real AI
        extraction contract, real repositories, real database. Only Twilio/OpenAI/Redis transport
        is swapped for synthetic events and inline execution.
      </p>

      <Panel title="Connection">
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
          <label style={labelStyle}>
            Access token
            <input
              style={inputStyle}
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
            />
          </label>
          <button style={buttonStyle} disabled={!token} onClick={lookupMyOrgs}>
            Look up my organizations
          </button>
          {myOrgs.length > 0 ? (
            <label style={labelStyle}>
              Organization
              <select style={inputStyle} value={orgId} onChange={(e) => setOrgId(e.target.value)}>
                {myOrgs.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.name}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <label style={labelStyle}>
              Organization ID
              <input style={inputStyle} value={orgId} onChange={(e) => setOrgId(e.target.value)} />
            </label>
          )}
        </div>
        {!connected && (
          <div style={{ color: "#f2b96b", fontSize: 12, marginTop: 6 }}>
            Sign up / log in via the API to get an access token, paste it above, then click
            &quot;Look up my organizations&quot;.
          </div>
        )}
      </Panel>

      <div style={{ display: "grid", gridTemplateColumns: "380px 1fr", gap: 16 }}>
        {/* --- Left column: Scenario Builder + Conversation Editor + Controls --- */}
        <div>
          <Panel title="Scenario Builder">
            <label style={labelStyle}>
              Preset
              <select
                style={inputStyle}
                onChange={(e) => {
                  const preset = PRESETS[e.target.value];
                  if (preset) {
                    setReq(preset);
                    setOverridesText("{}");
                  }
                }}
                defaultValue=""
              >
                <option value="" disabled>
                  Choose a preset…
                </option>
                {Object.keys(PRESETS).map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>

            <label style={labelStyle}>
              Workflow ({workflows.length || "…"} available)
              <select
                style={inputStyle}
                value={req.workflow}
                onChange={(e) => updateReq("workflow", e.target.value)}
              >
                {(workflows.length ? workflows : [{ name: req.workflow } as WorkflowInfo]).map(
                  (w) => (
                    <option key={w.name} value={w.name}>
                      {w.name}
                    </option>
                  )
                )}
              </select>
            </label>
            {workflows.find((w) => w.name === req.workflow) && (
              <div style={{ fontSize: 12, color: "#6f7f99", marginBottom: 8 }}>
                Trigger: {workflows.find((w) => w.name === req.workflow)!.trigger_event} · Steps:{" "}
                {workflows.find((w) => w.name === req.workflow)!.steps.join(" → ")}
              </div>
            )}

            <label style={labelStyle}>
              Business number (Twilio-side)
              <input
                style={inputStyle}
                value={req.business_number}
                onChange={(e) => updateReq("business_number", e.target.value)}
              />
            </label>
            <label style={labelStyle}>
              Caller number
              <input
                style={inputStyle}
                value={req.caller_number}
                onChange={(e) => updateReq("caller_number", e.target.value)}
              />
            </label>

            <label style={{ ...labelStyle, flexDirection: "row", alignItems: "center", gap: 8 }}>
              <input
                type="checkbox"
                checked={req.use_real_ai}
                onChange={(e) => updateReq("use_real_ai", e.target.checked)}
              />
              Use real OpenAI (default: deterministic mock, no cost)
            </label>

            <label style={labelStyle}>
              Business settings overrides / feature flags (JSON)
              <textarea
                style={{ ...inputStyle, height: 90, fontFamily: "monospace", fontSize: 12 }}
                value={overridesText}
                onChange={(e) => setOverridesText(e.target.value)}
              />
            </label>
          </Panel>

          <Panel title="Conversation Editor">
            {req.conversation_turns.map((turn, i) => (
              <div
                key={i}
                style={{
                  background: "#0b1020",
                  border: "1px solid #232d46",
                  borderRadius: 6,
                  padding: 8,
                  marginBottom: 6,
                  fontSize: 13,
                  display: "flex",
                  justifyContent: "space-between",
                  gap: 8,
                }}
              >
                <span>
                  <strong style={{ color: "#5a8fd6" }}>Customer:</strong> {turn}
                </span>
                <button
                  style={smallButtonStyle}
                  onClick={() =>
                    updateReq(
                      "conversation_turns",
                      req.conversation_turns.filter((_, idx) => idx !== i)
                    )
                  }
                >
                  ✕
                </button>
              </div>
            ))}
            <div style={{ display: "flex", gap: 6 }}>
              <input
                style={{ ...inputStyle, marginBottom: 0, flex: 1 }}
                placeholder='"My AC stopped working"'
                value={newTurn}
                onChange={(e) => setNewTurn(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && newTurn.trim()) {
                    updateReq("conversation_turns", [...req.conversation_turns, newTurn.trim()]);
                    setNewTurn("");
                  }
                }}
              />
              <button
                style={buttonStyle}
                onClick={() => {
                  if (newTurn.trim()) {
                    updateReq("conversation_turns", [...req.conversation_turns, newTurn.trim()]);
                    setNewTurn("");
                  }
                }}
              >
                Add
              </button>
            </div>
          </Panel>

          <Panel title="Controls">
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button style={primaryButtonStyle} disabled={!connected || busy} onClick={runSimulation}>
                ▶ Run
              </button>
              <button
                style={buttonStyle}
                disabled={!connected || busy || result?.workflow_run?.status !== "waiting_on_reply" && result?.workflow_run?.status !== "running"}
                onClick={stepForward}
              >
                ⏭ Step Forward
              </button>
              <button style={buttonStyle} disabled={busy} onClick={restart}>
                ↻ Restart
              </button>
              <button
                style={buttonStyle}
                disabled={!connected || busy || !result?.conversation_id}
                onClick={resetConversation}
              >
                🗑 Reset
              </button>
              <button style={buttonStyle} disabled={!connected || busy} onClick={saveScenario}>
                💾 Save Scenario
              </button>
            </div>
            {error && <div style={{ color: "#f26b6b", marginTop: 8, fontSize: 13 }}>{error}</div>}
          </Panel>

          <Panel title="Saved Scenarios">
            {scenarios.length === 0 && (
              <div style={{ color: "#6f7f99", fontSize: 13 }}>No saved scenarios yet.</div>
            )}
            {scenarios.map((s) => (
              <div
                key={s.id}
                style={{ display: "flex", justifyContent: "space-between", marginBottom: 6, fontSize: 13 }}
              >
                <button style={linkButtonStyle} onClick={() => loadScenario(s)}>
                  {s.name}
                </button>
                <button style={smallButtonStyle} onClick={() => deleteScenario(s.id)}>
                  ✕
                </button>
              </div>
            ))}
          </Panel>

          <Panel title="Event Replay">
            <div style={{ fontSize: 12, color: "#6f7f99", marginBottom: 6 }}>
              Republishes through the real EventBus, not a manual call.
            </div>
            {(result?.trace.events ?? []).map((e) => (
              <div key={e.seq} style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                <span style={{ fontSize: 12 }}>{String(e.event_type)}</span>
                <button
                  style={smallButtonStyle}
                  onClick={() => replayEvent(String(e.event_type), e.payload as Record<string, unknown>)}
                >
                  Replay
                </button>
              </div>
            ))}
            {!result?.trace.events.length && (
              <div style={{ color: "#6f7f99", fontSize: 12 }}>Run a simulation to see events here.</div>
            )}
          </Panel>
        </div>

        {/* --- Right column: Inspectors --- */}
        <div>
          {result?.workflow_run && (
            <div style={{ marginBottom: 12 }}>
              <Badge text={result.workflow_run.status} tone={result.workflow_run.status} />{" "}
              <span style={{ fontSize: 13, color: "#9fb0c9" }}>
                {result.workflow_run.workflow_name} — lead: {result.lead?.classification ?? "n/a"}
              </span>
            </div>
          )}

          <Panel title="Timeline">
            <Timeline records={result?.trace.timeline ?? []} />
          </Panel>

          <Panel title="Workflow Inspector">
            <WorkflowInspector steps={result?.trace.workflow_steps ?? []} />
          </Panel>

          <Panel title="Workflow State (workflow_runs.state)">
            <JsonBlock data={result?.workflow_run?.state ?? {}} />
          </Panel>

          <Panel title="Event Bus Inspector">
            <EventBusInspector
              events={result?.trace.events ?? []}
              subscribers={result?.trace.subscribers ?? []}
            />
          </Panel>

          <Panel title="AI Extraction Viewer">
            <AIExtractionViewer calls={result?.trace.ai_calls ?? []} />
          </Panel>

          <Panel title="Queue Inspector">
            <QueueInspector jobs={result?.trace.queue_jobs ?? []} />
          </Panel>

          <Panel title="Database Changes (read-only)">
            <DbChangesInspector changes={result?.trace.db_changes ?? []} />
          </Panel>

          <Panel title="API Inspector">
            <ApiInspector calls={apiCalls} />
          </Panel>
        </div>
      </div>
    </main>
  );
}

function mergeTrace(
  prev: SimulationRunResponse["trace"],
  next: SimulationRunResponse["trace"]
): SimulationRunResponse["trace"] {
  return {
    events: [...prev.events, ...next.events],
    subscribers: [...prev.subscribers, ...next.subscribers],
    workflow_steps: [...prev.workflow_steps, ...next.workflow_steps],
    queue_jobs: [...prev.queue_jobs, ...next.queue_jobs],
    ai_calls: [...prev.ai_calls, ...next.ai_calls],
    db_changes: [...prev.db_changes, ...next.db_changes],
    sms: [...prev.sms, ...next.sms],
    timeline: [...prev.timeline, ...next.timeline],
  };
}

const labelStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  fontSize: 12,
  color: "#9fb0c9",
  marginBottom: 10,
  flex: 1,
  minWidth: 160,
};

const inputStyle: React.CSSProperties = {
  marginTop: 4,
  background: "#0b1020",
  border: "1px solid #232d46",
  borderRadius: 6,
  color: "#e7ecf5",
  padding: "6px 8px",
  fontSize: 13,
};

const buttonStyle: React.CSSProperties = {
  background: "#1b2338",
  border: "1px solid #2f3a5a",
  borderRadius: 6,
  color: "#e7ecf5",
  padding: "6px 12px",
  fontSize: 13,
  cursor: "pointer",
};

const primaryButtonStyle: React.CSSProperties = {
  ...buttonStyle,
  background: "#2a5fd6",
  border: "1px solid #3a6fe6",
  fontWeight: 600,
};

const smallButtonStyle: React.CSSProperties = {
  ...buttonStyle,
  padding: "2px 8px",
  fontSize: 12,
};

const linkButtonStyle: React.CSSProperties = {
  background: "none",
  border: "none",
  color: "#5a8fd6",
  cursor: "pointer",
  padding: 0,
  fontSize: 13,
  textAlign: "left",
};
