import { useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";
import { ArtifactExplorer } from "../../components/ArtifactExplorer";
import { Badge } from "../../components/Badge";
import { JsonInspector } from "../../components/JsonInspector";
import type {
  EnvironmentSummary,
  Hypothesis,
  IncidentInvestigation,
  IncidentSummary,
  OperationalProfileSpec,
  ProbeIntent
} from "../../types";

type Tab = "summary" | "causal" | "hypotheses" | "evidence" | "probes" | "timeline" | "certificate" | "artifacts";

function tone(status?: string | null): "neutral" | "positive" | "negative" | "warning" | "accent" {
  if (!status) return "neutral";
  if (["root_cause_identified", "diagnosed", "proven", "completed"].includes(status)) return "positive";
  if (["ruled_out", "contradicted", "failed", "unhealthy"].includes(status)) return "negative";
  if (["insufficient_evidence", "multiple_plausible_causes", "candidate", "supported", "investigating"].includes(status)) return "warning";
  return "accent";
}

function confidence(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function sortHypotheses(items: Hypothesis[]): Hypothesis[] {
  return [...items].sort((left, right) => right.confidence - left.confidence || left.family_id.localeCompare(right.family_id));
}

export function IncidentWorkbench() {
  const [incidents, setIncidents] = useState<IncidentSummary[]>([]);
  const [incident, setIncident] = useState<IncidentInvestigation | null>(null);
  const [environments, setEnvironments] = useState<EnvironmentSummary[]>([]);
  const [profiles, setProfiles] = useState<OperationalProfileSpec[]>([]);
  const [selectedEnvironment, setSelectedEnvironment] = useState("");
  const [selectedProfile, setSelectedProfile] = useState("local-development-usable.v1");
  const [tab, setTab] = useState<Tab>("summary");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showOpen, setShowOpen] = useState(false);

  const refresh = async () => {
    const next = await api.incidents();
    setIncidents(next);
    if (!incident && next[0]) await openIncident(next[0].incident_id);
  };

  useEffect(() => {
    Promise.all([api.incidents(), api.environments(), api.operationalProfiles()])
      .then(async ([nextIncidents, nextEnvironments, nextProfiles]) => {
        setIncidents(nextIncidents);
        setEnvironments(nextEnvironments);
        setProfiles(nextProfiles);
        if (nextEnvironments[0]) setSelectedEnvironment(nextEnvironments[0].environment_id);
        if (nextIncidents[0]) setIncident(await api.incident(nextIncidents[0].incident_id));
      })
      .catch((reason: Error) => setError(reason.message));
  }, []);

  const openIncident = async (incidentId: string) => {
    setBusy("open");
    setError(null);
    try {
      setIncident(await api.incident(incidentId));
      setTab("summary");
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const createIncident = async () => {
    const environment = environments.find((item) => item.environment_id === selectedEnvironment);
    const snapshotId = environment?.latest_snapshot?.snapshot_id;
    if (!snapshotId) {
      setError("The selected environment has no snapshot. Collect one from the Environments workbench first.");
      return;
    }
    setBusy("create");
    setError(null);
    try {
      const created = await api.openIncident(snapshotId, { profile_id: selectedProfile, evidence_budget: 5 });
      setIncident(created);
      setShowOpen(false);
      setTab("summary");
      await refresh();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const runProbe = async (probe: ProbeIntent) => {
    if (!incident) return;
    setBusy(probe.probe_id);
    setError(null);
    try {
      const refined = await api.runProbe(incident.incident_id, probe.probe_id);
      setIncident(refined);
      setTab("summary");
      setIncidents(await api.incidents());
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const hypotheses = useMemo(() => sortHypotheses(incident?.hypotheses ?? []), [incident]);
  const roots = new Set(incident?.certificate?.root_cause_hypothesis_ids ?? []);
  const evidenceById = useMemo(() => new Map((incident?.evidence ?? []).map((item) => [item.evidence_id, item])), [incident]);
  const symptomById = useMemo(() => new Map((incident?.symptoms ?? []).map((item) => [item.symptom_id, item])), [incident]);

  return (
    <main className="incident-workbench">
      <aside className="incident-rail">
        <div className="rail-heading">
          <span className="eyebrow">Read-only investigation</span>
          <h2>Incidents</h2>
          <p>Trace violated contracts into evidence-backed causal hypotheses.</p>
        </div>
        <button type="button" className="button primary full-button" onClick={() => setShowOpen((value) => !value)}>
          {showOpen ? "Close incident form" : "Open from snapshot"}
        </button>
        {showOpen && (
          <div className="incident-create-form">
            <label className="field"><span>Environment</span>
              <select value={selectedEnvironment} onChange={(event: React.ChangeEvent<HTMLSelectElement>) => setSelectedEnvironment(event.target.value)}>
                {environments.map((item) => <option key={item.environment_id} value={item.environment_id}>{item.name}</option>)}
              </select>
            </label>
            <label className="field"><span>Operational profile</span>
              <select value={selectedProfile} onChange={(event: React.ChangeEvent<HTMLSelectElement>) => setSelectedProfile(event.target.value)}>
                {profiles.map((item) => <option key={item.profile_id} value={item.profile_id}>{item.title}</option>)}
              </select>
            </label>
            <button type="button" className="button primary full-button" disabled={busy === "create"} onClick={createIncident}>
              {busy === "create" ? "Opening…" : "Open investigation"}
            </button>
          </div>
        )}
        <div className="incident-list">
          {incidents.map((item) => (
            <button type="button" key={item.incident_id} className={incident?.incident_id === item.incident_id ? "is-selected" : ""} onClick={() => void openIncident(item.incident_id)}>
              <span><strong>{item.title}</strong><small>{item.environment_id} · {item.hypothesis_count} hypotheses</small></span>
              <span className="incident-list-status"><Badge tone={tone(item.certificate_status)}>{item.certificate_status ?? item.status}</Badge><small>{confidence(item.confidence)}</small></span>
            </button>
          ))}
          {incidents.length === 0 && <div className="empty-state">No investigations have been opened.</div>}
        </div>
      </aside>

      <section className="incident-main">
        {error && <div className="error-banner">{error}</div>}
        {!incident ? (
          <div className="empty-state large">Open an incident from an environment snapshot.</div>
        ) : (
          <>
            <header className="incident-header">
              <div>
                <span className="eyebrow">{incident.environment_id} · {incident.profile_id}</span>
                <h1>{incident.title}</h1>
                <p>{incident.initial_symptom}</p>
              </div>
              <div className="incident-header-badges">
                <Badge tone={tone(incident.status)}>{incident.status}</Badge>
                <Badge tone={tone(incident.certificate?.status)}>{incident.certificate?.status ?? "uncertified"}</Badge>
                <Badge tone="accent">{confidence(incident.certificate?.confidence ?? 0)}</Badge>
                <Badge>{incident.probe_plan?.probes.length ?? 0} probes</Badge>
              </div>
            </header>

            <nav className="subnav" aria-label="Incident workspace">
              {(["summary", "causal", "hypotheses", "evidence", "probes", "timeline", "certificate", "artifacts"] as Tab[]).map((item) => (
                <button type="button" key={item} className={tab === item ? "active" : ""} onClick={() => setTab(item)}>{item}</button>
              ))}
            </nav>

            {tab === "summary" && (
              <div className="incident-summary-grid">
                <section className="panel incident-metrics">
                  <h3>Investigation state</h3>
                  <div className="metric-grid">
                    <div><small>Violated invariants</small><strong>{incident.violated_invariant_ids.length}</strong></div>
                    <div><small>Symptoms</small><strong>{incident.symptoms.length}</strong></div>
                    <div><small>Evidence facts</small><strong>{incident.evidence.length}</strong></div>
                    <div><small>Hypotheses</small><strong>{incident.hypotheses.length}</strong></div>
                  </div>
                </section>
                <section className="panel">
                  <h3>Leading explanations</h3>
                  <div className="hypothesis-stack compact">
                    {hypotheses.slice(0, 5).map((item) => (
                      <article key={item.hypothesis_id} className={roots.has(item.hypothesis_id) ? "root-hypothesis" : ""}>
                        <div><Badge tone={tone(item.status)}>{item.status}</Badge><Badge>{confidence(item.confidence)}</Badge>{roots.has(item.hypothesis_id) && <Badge tone="accent">root</Badge>}</div>
                        <strong>{String(item.metadata.title ?? item.family_id)}</strong>
                        <p>{item.claim}</p>
                      </article>
                    ))}
                  </div>
                </section>
                <section className="panel">
                  <h3>Remaining uncertainty</h3>
                  {incident.certificate?.unresolved_questions.length ? (
                    <ul className="plain-list">{incident.certificate.unresolved_questions.map((item) => <li key={item}>{item}</li>)}</ul>
                  ) : <div className="empty-state">No unresolved evidence intents remain.</div>}
                </section>
                <section className="panel">
                  <h3>Recommended next probe</h3>
                  {incident.probe_plan?.probes[0] ? <ProbeCard probe={incident.probe_plan.probes[0]} busy={busy} onRun={runProbe} /> : <div className="empty-state">{incident.probe_plan?.stopping_reason ?? "No probe is currently required."}</div>}
                </section>
              </div>
            )}

            {tab === "causal" && (
              <div className="causal-workspace">
                <section className="causal-column">
                  <h3>Evidence</h3>
                  {incident.causal_edges.filter((edge) => edge.relation === "supports" || edge.relation === "contradicts").slice(0, 30).map((edge) => {
                    const evidence = evidenceById.get(edge.source_id);
                    return <article key={edge.edge_id} className={`causal-node ${edge.relation}`}><Badge tone={edge.relation === "supports" ? "positive" : "negative"}>{edge.relation}</Badge><strong>{evidence?.fact_type ?? edge.source_id}</strong><p>{edge.statement}</p></article>;
                  })}
                </section>
                <section className="causal-column central">
                  <h3>Hypotheses</h3>
                  {hypotheses.map((item) => <article key={item.hypothesis_id} className={`causal-node hypothesis ${roots.has(item.hypothesis_id) ? "root-hypothesis" : ""}`}><div><Badge tone={tone(item.status)}>{item.status}</Badge><Badge>{confidence(item.confidence)}</Badge></div><strong>{item.family_id}</strong><p>{item.claim}</p></article>)}
                </section>
                <section className="causal-column">
                  <h3>Symptoms and propagation</h3>
                  {incident.symptoms.map((item) => <article key={item.symptom_id} className="causal-node symptom"><Badge tone="negative">{item.health_status ?? "symptom"}</Badge><strong>{item.invariant_family ?? item.symptom_type}</strong><p>{item.statement}</p></article>)}
                  {incident.causal_edges.filter((edge) => edge.relation === "propagates_to").map((edge) => <article key={edge.edge_id} className="causal-node propagation"><Badge tone="warning">propagation</Badge><p>{edge.statement}</p></article>)}
                </section>
              </div>
            )}

            {tab === "hypotheses" && <div className="hypothesis-stack">{hypotheses.map((item) => <HypothesisCard key={item.hypothesis_id} item={item} root={roots.has(item.hypothesis_id)} evidenceById={evidenceById} symptomById={symptomById} />)}</div>}

            {tab === "evidence" && (
              <div className="evidence-table-wrap"><table className="data-table"><thead><tr><th>Fact</th><th>Statement</th><th>Subjects</th><th>Collector</th><th>Authority</th></tr></thead><tbody>{incident.evidence.map((item) => <tr key={item.evidence_id}><td><code>{item.fact_type}</code></td><td>{item.statement}</td><td>{item.subject_ids.join(", ") || "—"}</td><td>{item.collector_id}</td><td><Badge tone={item.authority === "authoritative" ? "positive" : "warning"}>{item.authority}</Badge></td></tr>)}</tbody></table></div>
            )}

            {tab === "probes" && (
              <div className="probe-layout">
                <section><h3>Recommended probes</h3><div className="probe-stack">{incident.probe_plan?.probes.map((probe) => <ProbeCard key={probe.probe_id} probe={probe} busy={busy} onRun={runProbe} />)}{!incident.probe_plan?.probes.length && <div className="empty-state">{incident.probe_plan?.stopping_reason ?? "No probe recommendations."}</div>}</div></section>
                <section><h3>Probe history</h3><div className="timeline-list">{incident.probe_runs.map((run) => <article key={run.probe_run_id}><Badge tone={tone(run.status)}>{run.status}</Badge><strong>{run.probe.title}</strong><p>{run.evidence_ids.length} facts · {Object.keys(run.hypothesis_changes).length} changed hypotheses</p></article>)}{incident.probe_runs.length === 0 && <div className="empty-state">No probes have run.</div>}</div></section>
              </div>
            )}

            {tab === "timeline" && <div className="incident-timeline">{incident.timeline.map((entry) => <article key={entry.sequence}><div className="timeline-marker">{entry.sequence}</div><div><small>{new Date(entry.occurred_at_iso).toLocaleString()}</small><strong>{entry.title}</strong><Badge>{entry.event_type}</Badge><JsonInspector value={entry.details} /></div></article>)}</div>}
            {tab === "certificate" && <JsonInspector value={incident.certificate} emptyLabel="No diagnosis certificate has been issued." />}
            {tab === "artifacts" && <ArtifactExplorer artifacts={incident.artifacts ?? []} />}
          </>
        )}
      </section>
    </main>
  );
}

function ProbeCard({ probe, busy, onRun }: { probe: ProbeIntent; busy: string | null; onRun: (probe: ProbeIntent) => void }) {
  return <article className="probe-card"><div className="probe-card-heading"><div><Badge tone="accent">IG {probe.information_gain_score.toFixed(2)}</Badge><Badge>{probe.risk_class}</Badge><Badge>cost {probe.cost_score}</Badge></div><strong>{probe.title}</strong></div><p>{probe.rationale}</p><small>{probe.candidate_collector_ids.join(" → ")}</small><button type="button" className="button primary" disabled={busy === probe.probe_id} onClick={() => onRun(probe)}>{busy === probe.probe_id ? "Collecting…" : "Run read-only probe"}</button></article>;
}

function HypothesisCard({ item, root, evidenceById, symptomById }: { item: Hypothesis; root: boolean; evidenceById: Map<string, IncidentInvestigation["evidence"][number]>; symptomById: Map<string, IncidentInvestigation["symptoms"][number]> }) {
  return <article className={`hypothesis-card ${root ? "root-hypothesis" : ""}`}><header><div><Badge tone={tone(item.status)}>{item.status}</Badge><Badge>{confidence(item.confidence)}</Badge>{root && <Badge tone="accent">certificate root</Badge>}</div><h3>{String(item.metadata.title ?? item.family_id)}</h3><p>{item.claim}</p></header><div className="hypothesis-detail-grid"><div><h4>Explains</h4>{item.explains_symptom_ids.map((id) => <p key={id}>{symptomById.get(id)?.statement ?? id}</p>)}</div><div><h4>Supporting evidence</h4>{item.supporting_evidence_ids.map((id) => <p key={id}>{evidenceById.get(id)?.statement ?? id}</p>)}{item.supporting_evidence_ids.length === 0 && <p>None collected.</p>}</div><div><h4>Contradictions</h4>{item.contradicting_evidence_ids.map((id) => <p key={id}>{evidenceById.get(id)?.statement ?? id}</p>)}{item.contradicting_evidence_ids.length === 0 && <p>None.</p>}</div><div><h4>Missing predictions</h4>{item.predictions.map((prediction) => <code key={prediction}>{prediction}</code>)}{item.predictions.length === 0 && <p>All predicted evidence is represented.</p>}</div></div></article>;
}
