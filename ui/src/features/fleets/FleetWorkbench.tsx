import { useEffect, useMemo, useState } from "react";
import type { ChangeEvent } from "react";
import { api } from "../../api/client";
import { Badge } from "../../components/Badge";
import { JsonInspector } from "../../components/JsonInspector";
import type { FleetAssessment, FleetDefinition, FleetOperationPlan } from "../../types";

function tone(status?: string): "positive" | "negative" | "warning" | "neutral" | "accent" {
  if (status === "healthy" || status === "complete") return "positive";
  if (status === "unavailable" || status === "failed") return "negative";
  if (status === "degraded" || status === "unknown" || status === "recovering") return "warning";
  return "neutral";
}

export function FleetWorkbench() {
  const [fleets, setFleets] = useState<FleetDefinition[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [assessment, setAssessment] = useState<FleetAssessment | null>(null);
  const [plan, setPlan] = useState<FleetOperationPlan | null>(null);
  const [operationType, setOperationType] = useState("maintenance");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.fleets().then((items) => {
      setFleets(items);
      setSelectedId(items[0]?.fleet_id ?? null);
    }).catch((reason: Error) => setError(reason.message));
  }, []);

  const fleet = useMemo(() => fleets.find((item) => item.fleet_id === selectedId) ?? null, [fleets, selectedId]);

  const assess = async () => {
    if (!fleet) return;
    setBusy("assess"); setError(null);
    try { setAssessment((await api.assessFleet(fleet.fleet_id)).assessment); }
    catch (reason) { setError((reason as Error).message); }
    finally { setBusy(null); }
  };

  const compilePlan = async () => {
    if (!fleet) return;
    setBusy("plan"); setError(null);
    try { setPlan(await api.planFleetOperation(fleet.fleet_id, operationType)); }
    catch (reason) { setError((reason as Error).message); }
    finally { setBusy(null); }
  };

  if (error && fleets.length === 0) return <main className="startup-error"><h1>Fleet control unavailable</h1><p>{error}</p></main>;
  if (!fleet) return <main className="startup-loading">Loading fleet registry…</main>;

  return <main className="fleet-workbench">
    <aside className="fleet-rail">
      <div className="section-heading"><div><small>Release 1.0</small><h2>Fleet Control</h2></div><Badge tone="accent">{fleets.length}</Badge></div>
      <p className="muted">Cross-cluster health, common causes, and dependency-ordered operation waves.</p>
      <div className="fleet-list">{fleets.map((item) => <button type="button" key={item.fleet_id} className={item.fleet_id === selectedId ? "is-selected" : ""} onClick={() => { setSelectedId(item.fleet_id); setAssessment(null); setPlan(null); }}><span><strong>{item.name}</strong><small>{item.members.length} environments · {item.dependencies.length} dependencies</small></span><Badge tone={item.active ? "positive" : "neutral"}>{item.active ? "active" : "inactive"}</Badge></button>)}</div>
    </aside>
    <section className="fleet-main">
      <header className="fleet-header"><div><small>{fleet.organization_id} / {fleet.workspace_id}</small><h1>{fleet.name}</h1><p>{fleet.fleet_id}</p></div><div className="fleet-controls"><button type="button" className="button primary" disabled={busy !== null} onClick={assess}>{busy === "assess" ? "Assessing…" : "Assess fleet"}</button><select value={operationType} onChange={(event: ChangeEvent<HTMLSelectElement>) => setOperationType(event.target.value)}><option value="startup">Startup</option><option value="shutdown">Shutdown</option><option value="maintenance">Maintenance</option><option value="recovery">Recovery</option><option value="verification">Verification</option></select><button type="button" className="button" disabled={busy !== null} onClick={compilePlan}>{busy === "plan" ? "Planning…" : "Compile waves"}</button></div></header>
      {error && <div className="error-banner">{error}</div>}
      <div className="fleet-grid">
        <section className="panel"><div className="section-heading"><h2>Fleet topology</h2><Badge tone="accent">parallel {fleet.max_parallel_operations}</Badge></div><div className="metric-grid"><div><small>Members</small><strong>{fleet.members.length}</strong></div><div><small>Dependencies</small><strong>{fleet.dependencies.length}</strong></div><div><small>Failure domains</small><strong>{new Set(fleet.members.map((item) => item.failure_domain).filter(Boolean)).size}</strong></div><div><small>Critical members</small><strong>{fleet.members.filter((item) => item.criticality === "critical").length}</strong></div></div><div className="fleet-member-list">{fleet.members.map((member) => <article key={member.environment_id}><div><strong>{member.environment_id}</strong><small>{member.failure_domain ?? "unassigned failure domain"}</small></div><Badge tone={member.criticality === "critical" ? "warning" : "neutral"}>{member.criticality}</Badge></article>)}</div></section>
        <section className="panel"><div className="section-heading"><h2>Dependency graph</h2></div>{fleet.dependencies.length ? <div className="dependency-list">{fleet.dependencies.map((dependency) => <article key={dependency.dependency_id}><code>{dependency.source_environment_id}</code><span>→</span><code>{dependency.target_environment_id}</code><Badge tone="accent">{dependency.relationship_type}</Badge></article>)}</div> : <p className="muted">No cross-environment dependencies.</p>}</section>
      </div>
      {assessment && <section className="panel fleet-assessment"><div className="section-heading"><div><small>Latest assessment</small><h2>{assessment.assessment_id}</h2></div><Badge tone={tone(assessment.status)}>{assessment.status}</Badge></div><div className="metric-grid"><div><small>Healthy</small><strong>{assessment.summary.healthy ?? 0}</strong></div><div><small>Degraded</small><strong>{assessment.summary.degraded ?? 0}</strong></div><div><small>Unavailable</small><strong>{assessment.summary.unavailable ?? 0}</strong></div><div><small>Common causes</small><strong>{assessment.common_causes.length}</strong></div></div><div className="fleet-status-grid">{assessment.environments.map((item) => <article key={item.environment_id}><header><strong>{item.environment_id}</strong><Badge tone={tone(item.status)}>{item.status}</Badge></header><small>{item.active_incident_ids.length} incidents · {item.active_operation_ids.length} operations</small>{item.reasons.map((reason) => <p key={reason}>{reason}</p>)}</article>)}</div>{assessment.common_causes.length > 0 && <div className="common-cause-list">{assessment.common_causes.map((finding) => <article key={finding.finding_id}><Badge tone="warning">{Math.round(finding.confidence * 100)}%</Badge><div><strong>{finding.title}</strong><small>{finding.environment_ids.join(" · ")}</small></div></article>)}</div>}</section>}
      {plan && <section className="panel"><div className="section-heading"><div><small>{plan.operation_type} plan</small><h2>Dependency-ordered waves</h2></div><Badge tone="accent">{plan.waves.length} waves</Badge></div><div className="fleet-waves">{plan.waves.map((wave) => <article key={wave.wave_index}><div className="wave-number">{wave.wave_index + 1}</div><div><strong>{wave.environment_ids.join(", ")}</strong><small>{wave.rationale.join(" · ") || "No additional rationale"}</small>{wave.blocked_by_environment_ids.length > 0 && <p>Blocked by: {wave.blocked_by_environment_ids.join(", ")}</p>}</div></article>)}</div>{plan.warnings.length > 0 && <JsonInspector value={plan.warnings} />}</section>}
    </section>
  </main>;
}
