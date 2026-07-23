import { useEffect, useMemo, useState } from "react";
import type { ChangeEvent } from "react";
import { api } from "../../api/client";
import { ArtifactExplorer } from "../../components/ArtifactExplorer";
import { Badge } from "../../components/Badge";
import { EnvironmentTopology } from "../../components/EnvironmentTopology";
import { JsonInspector } from "../../components/JsonInspector";
import type {
  AccessValidation,
  EnvironmentDefinition,
  EnvironmentSnapshot,
  EnvironmentSummary,
  OperationalProfileAssessment,
  OperationalProfileSpec,
  SnapshotDiff,
  SnapshotSummary,
  TopologyGraph
} from "../../types";

type Tab = "overview" | "inventory" | "topology" | "health" | "snapshots" | "artifacts";

const emptyEnvironment = (): EnvironmentDefinition => ({
  environment_id: "",
  name: "",
  environment_class: "development",
  provider: "local",
  cluster_provider: "kind",
  host_provider: "docker",
  criticality: "disposable",
  access_methods: [
    {
      method_id: "default",
      method_type: "kubectl",
      title: "Local kubectl context",
      context_name: "",
      kubeconfig_path: "",
      fixture_path: "",
      command: "kubectl",
      read_only: true,
      timeout_seconds: 30,
      metadata: {}
    }
  ],
  default_access_method_id: "default",
  operational_profile_ids: ["cluster-observable.v1", "local-development-usable.v1"],
  installed_pack_ids: ["generic-kubernetes", "kind"],
  labels: {},
  annotations: {},
  metadata: {}
});

function tone(status?: string | null): "positive" | "negative" | "warning" | "accent" | "neutral" {
  if (status === "healthy" || status === "complete") return "positive";
  if (status === "unhealthy" || status === "failed") return "negative";
  if (status === "degraded" || status === "partial" || status === "unknown" || status === "pending") return "warning";
  return "neutral";
}

function latestAssessment(environment: EnvironmentSummary | null) {
  if (!environment?.latest_health?.length) return null;
  return environment.latest_health.find((item) => item.profile_id === "local-development-usable.v1") ?? environment.latest_health[0];
}

export function EnvironmentWorkbench() {
  const [environments, setEnvironments] = useState<EnvironmentSummary[]>([]);
  const [profiles, setProfiles] = useState<OperationalProfileSpec[]>([]);
  const [selectedEnvironmentId, setSelectedEnvironmentId] = useState<string | null>(null);
  const [environment, setEnvironment] = useState<EnvironmentDefinition | null>(null);
  const [snapshots, setSnapshots] = useState<SnapshotSummary[]>([]);
  const [snapshot, setSnapshot] = useState<EnvironmentSnapshot | null>(null);
  const [topology, setTopology] = useState<TopologyGraph | null>(null);
  const [diff, setDiff] = useState<SnapshotDiff | null>(null);
  const [validation, setValidation] = useState<AccessValidation | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [draft, setDraft] = useState<EnvironmentDefinition>(emptyEnvironment());
  const [inventorySearch, setInventorySearch] = useState("");
  const [inventoryNamespace, setInventoryNamespace] = useState("all");

  const refreshEnvironments = async () => {
    const next = await api.environments();
    setEnvironments(next);
    if (!selectedEnvironmentId && next[0]) setSelectedEnvironmentId(next[0].environment_id);
  };

  useEffect(() => {
    Promise.all([api.environments(), api.operationalProfiles()])
      .then(([nextEnvironments, nextProfiles]) => {
        setEnvironments(nextEnvironments);
        setProfiles(nextProfiles);
        if (nextEnvironments[0]) setSelectedEnvironmentId(nextEnvironments[0].environment_id);
      })
      .catch((reason: Error) => setError(reason.message));
  }, []);

  useEffect(() => {
    if (!selectedEnvironmentId) return;
    setError(null);
    setSnapshot(null);
    setTopology(null);
    setDiff(null);
    Promise.all([api.environment(selectedEnvironmentId), api.snapshots(selectedEnvironmentId)])
      .then(([nextEnvironment, nextSnapshots]) => {
        setEnvironment(nextEnvironment);
        setSnapshots(nextSnapshots);
        setValidation(nextEnvironment.latest_validation ?? null);
        if (nextSnapshots[0]) {
          void openSnapshot(nextSnapshots[0].snapshot_id, nextSnapshots);
        }
      })
      .catch((reason: Error) => setError(reason.message));
  }, [selectedEnvironmentId]);

  const openSnapshot = async (snapshotId: string, knownSnapshots = snapshots) => {
    setBusy("snapshot");
    setError(null);
    try {
      const [nextSnapshot, nextTopology] = await Promise.all([api.snapshot(snapshotId), api.topology(snapshotId)]);
      setSnapshot(nextSnapshot);
      setTopology(nextTopology);
      const currentIndex = knownSnapshots.findIndex((item) => item.snapshot_id === snapshotId);
      const before = currentIndex >= 0 ? knownSnapshots[currentIndex + 1]?.snapshot_id : undefined;
      if (before) {
        try {
          setDiff(await api.snapshotDiff(snapshotId, before));
        } catch {
          setDiff(null);
        }
      } else {
        setDiff(null);
      }
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const validate = async () => {
    if (!selectedEnvironmentId) return;
    setBusy("validate");
    setError(null);
    try {
      const result = await api.validateEnvironment(selectedEnvironmentId, environment?.default_access_method_id ?? undefined);
      setValidation(result);
      await refreshEnvironments();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const collect = async () => {
    if (!selectedEnvironmentId) return;
    setBusy("collect");
    setError(null);
    try {
      const result = await api.collectSnapshot(selectedEnvironmentId, {
        method_id: environment?.default_access_method_id,
        profile_ids: environment?.operational_profile_ids
      });
      const nextSnapshots = await api.snapshots(selectedEnvironmentId);
      setSnapshots(nextSnapshots);
      setSnapshot(result);
      setTopology(result.topology ?? await api.topology(result.snapshot_id));
      setDiff(result.diff_from_previous ?? null);
      await refreshEnvironments();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const createEnvironment = async () => {
    setBusy("create");
    setError(null);
    try {
      const method = draft.access_methods[0];
      const cleanedMethod = {
        ...method,
        context_name: method.context_name || null,
        kubeconfig_path: method.kubeconfig_path || null,
        fixture_path: method.fixture_path || null
      };
      const payload = { ...draft, access_methods: [cleanedMethod] };
      const created = await api.createEnvironment(payload);
      setShowCreate(false);
      setDraft(emptyEnvironment());
      await refreshEnvironments();
      setSelectedEnvironmentId(created.environment_id);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const selectedSummary = environments.find((item) => item.environment_id === selectedEnvironmentId) ?? null;
  const health = snapshot?.assessments ?? selectedSummary?.latest_health ?? [];
  const primaryHealth = health.find((item) => item.profile_id === "local-development-usable.v1") ?? health[0] ?? latestAssessment(selectedSummary);
  const namespaces = useMemo(
    () => Array.from(new Set((snapshot?.entities ?? []).map((item) => item.namespace ?? "_cluster"))).sort(),
    [snapshot]
  );
  const inventory = useMemo(() => {
    const query = inventorySearch.toLowerCase();
    return (snapshot?.entities ?? []).filter((entity) => {
      if (inventoryNamespace !== "all" && (entity.namespace ?? "_cluster") !== inventoryNamespace) return false;
      return !query || `${entity.name} ${entity.entity_type} ${entity.entity_id}`.toLowerCase().includes(query);
    });
  }, [snapshot, inventorySearch, inventoryNamespace]);

  return (
    <main className="environment-workbench">
      <aside className="environment-rail">
        <div className="rail-heading">
          <span className="eyebrow">Read-only intelligence</span>
          <h2>Environments</h2>
          <p>Register targets, validate observer access, and inspect immutable snapshots.</p>
        </div>
        <button type="button" className="button primary full-button" onClick={() => setShowCreate((value) => !value)}>
          {showCreate ? "Close registration" : "Register environment"}
        </button>
        {showCreate && (
          <div className="environment-create-form">
            <label className="field"><span>Environment ID</span><input value={draft.environment_id} onChange={(event: ChangeEvent<HTMLInputElement>) => setDraft({ ...draft, environment_id: event.target.value })} placeholder="local-kind" /></label>
            <label className="field"><span>Name</span><input value={draft.name} onChange={(event: ChangeEvent<HTMLInputElement>) => setDraft({ ...draft, name: event.target.value })} placeholder="Local Kind" /></label>
            <label className="field"><span>Environment class</span><select value={draft.environment_class} onChange={(event: ChangeEvent<HTMLSelectElement>) => setDraft({ ...draft, environment_class: event.target.value as EnvironmentDefinition["environment_class"] })}><option value="development">Development</option><option value="staging">Staging</option><option value="production">Production</option><option value="simulation">Simulation</option></select></label>
            <label className="field"><span>Cluster provider</span><input value={draft.cluster_provider} onChange={(event: ChangeEvent<HTMLInputElement>) => setDraft({ ...draft, cluster_provider: event.target.value })} /></label>
            <label className="field"><span>Access source</span><select value={draft.access_methods[0].method_type} onChange={(event: ChangeEvent<HTMLSelectElement>) => setDraft({ ...draft, access_methods: [{ ...draft.access_methods[0], method_type: event.target.value as "kubectl" | "kubeconfig" | "fixture" }] })}><option value="kubectl">kubectl</option><option value="kubeconfig">kubeconfig</option><option value="fixture">Fixture</option></select></label>
            {draft.access_methods[0].method_type === "fixture" ? (
              <label className="field"><span>Fixture path</span><input value={draft.access_methods[0].fixture_path ?? ""} onChange={(event: ChangeEvent<HTMLInputElement>) => setDraft({ ...draft, access_methods: [{ ...draft.access_methods[0], fixture_path: event.target.value }] })} placeholder="lab/fixtures/example.yaml" /></label>
            ) : (
              <>
                <label className="field"><span>Context</span><input value={draft.access_methods[0].context_name ?? ""} onChange={(event: ChangeEvent<HTMLInputElement>) => setDraft({ ...draft, access_methods: [{ ...draft.access_methods[0], context_name: event.target.value }] })} placeholder="kind-local" /></label>
                <label className="field"><span>Kubeconfig path</span><input value={draft.access_methods[0].kubeconfig_path ?? ""} onChange={(event: ChangeEvent<HTMLInputElement>) => setDraft({ ...draft, access_methods: [{ ...draft.access_methods[0], kubeconfig_path: event.target.value }] })} placeholder="Optional" /></label>
              </>
            )}
            <button type="button" className="button primary full-button" disabled={!draft.environment_id || !draft.name || busy === "create"} onClick={createEnvironment}>{busy === "create" ? "Registering…" : "Register"}</button>
          </div>
        )}
        <div className="environment-list">
          {environments.map((item) => {
            const assessment = latestAssessment(item);
            return (
              <button type="button" key={item.environment_id} className={item.environment_id === selectedEnvironmentId ? "is-selected" : ""} onClick={() => setSelectedEnvironmentId(item.environment_id)}>
                <span><strong>{item.name}</strong><small>{item.cluster_provider} · {item.environment_class}</small></span>
                <Badge tone={tone(assessment?.status ?? item.latest_snapshot?.status)}>{assessment?.status ?? item.latest_snapshot?.status ?? "unobserved"}</Badge>
              </button>
            );
          })}
        </div>
      </aside>

      <section className="environment-main">
        {!environment ? (
          <div className="empty-state large">Register or select an environment.</div>
        ) : (
          <>
            <div className="environment-titlebar">
              <div>
                <span className="eyebrow">{environment.environment_class} · {environment.cluster_provider}</span>
                <h1>{environment.name}</h1>
                <p>{environment.environment_id} · Observer-only authority</p>
              </div>
              <div className="environment-actions">
                <button type="button" className="button secondary" disabled={Boolean(busy)} onClick={validate}>{busy === "validate" ? "Validating…" : "Validate access"}</button>
                <button type="button" className="button primary" disabled={Boolean(busy)} onClick={collect}>{busy === "collect" ? "Collecting…" : "Collect snapshot"}</button>
              </div>
            </div>
            {error && <div className="error-banner environment-error">{error}</div>}
            <div className="metric-strip environment-metrics">
              <div className="metric-card"><span>Environment health</span><strong>{primaryHealth?.status ?? "unknown"}</strong><small>{primaryHealth?.profile_id ?? "No profile assessment"}</small></div>
              <div className="metric-card"><span>Latest snapshot</span><strong>{snapshot?.status ?? selectedSummary?.latest_snapshot?.status ?? "none"}</strong><small>{snapshot ? new Date(snapshot.captured_at_iso).toLocaleString() : "No evidence captured"}</small></div>
              <div className="metric-card"><span>Entities</span><strong>{snapshot?.entities.length ?? selectedSummary?.latest_snapshot?.entity_count ?? 0}</strong><small>{snapshot?.relationships.length ?? selectedSummary?.latest_snapshot?.relationship_count ?? 0} relationships</small></div>
              <div className="metric-card"><span>Access</span><strong>{validation?.status ?? environment.latest_validation?.status ?? "unchecked"}</strong><small>{validation?.current_context ?? environment.default_access_method_id ?? "No method"}</small></div>
            </div>
            <nav className="workspace-tabs" aria-label="Environment workspace">
              {(["overview", "inventory", "topology", "health", "snapshots", "artifacts"] as Tab[]).map((item) => (
                <button type="button" key={item} className={tab === item ? "active" : ""} onClick={() => setTab(item)}>{item}</button>
              ))}
            </nav>

            {tab === "overview" && (
              <div className="workspace-grid">
                <section className="panel">
                  <div className="panel-heading compact"><div><span className="eyebrow">Target identity</span><h2>Access and provenance</h2></div><Badge tone={tone(validation?.status)}>{validation?.status ?? "unchecked"}</Badge></div>
                  {validation ? (
                    <div className="access-checks">
                      {validation.checks.map((check) => <div className="access-check" key={check.check_id}><Badge tone={tone(check.status)}>{check.status}</Badge><div><strong>{check.title}</strong><p>{check.explanation}</p></div></div>)}
                    </div>
                  ) : <div className="empty-state">Validate access to establish the target fingerprint and observer capability.</div>}
                </section>
                <section className="panel">
                  <div className="panel-heading compact"><div><span className="eyebrow">Snapshot quality</span><h2>Collection evidence</h2></div></div>
                  {snapshot ? (
                    <div className="summary-list">
                      <div><span>Source fingerprint</span><code>{snapshot.source_fingerprint}</code></div>
                      <div><span>Raw resources</span><strong>{snapshot.raw_resource_count}</strong></div>
                      <div><span>Permission gaps</span><strong>{snapshot.permission_gaps.length}</strong></div>
                      <div><span>Collection issues</span><strong>{snapshot.issues.length}</strong></div>
                      <div><span>Topology warnings</span><strong>{Array.isArray(snapshot.metadata.topology_warnings) ? snapshot.metadata.topology_warnings.length : 0}</strong></div>
                    </div>
                  ) : <div className="empty-state">Collect a snapshot to populate environment evidence.</div>}
                </section>
                <section className="panel span-two">
                  <div className="panel-heading compact"><div><span className="eyebrow">Change since prior observation</span><h2>Snapshot drift</h2></div>{diff && <Badge tone={Object.values(diff.summary).some(Boolean) ? "warning" : "positive"}>{Object.values(diff.summary).reduce((sum, value) => sum + value, 0)} changes</Badge>}</div>
                  {diff ? <DiffSummary diff={diff} /> : <div className="empty-state">A second snapshot is required for differential analysis.</div>}
                </section>
              </div>
            )}

            {tab === "inventory" && (
              <section className="panel">
                <div className="panel-heading"><div><span className="eyebrow">Normalized resources</span><h2>Environment inventory</h2><p>Sanitized API objects projected into provider-neutral operational entities.</p></div></div>
                <div className="inventory-toolbar">
                  <label className="field compact-control"><span>Search</span><input value={inventorySearch} onChange={(event: ChangeEvent<HTMLInputElement>) => setInventorySearch(event.target.value)} /></label>
                  <label className="field compact-control"><span>Namespace</span><select value={inventoryNamespace} onChange={(event: ChangeEvent<HTMLSelectElement>) => setInventoryNamespace(event.target.value)}><option value="all">All</option>{namespaces.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
                  <Badge tone="accent">{inventory.length} visible</Badge>
                </div>
                <div className="inventory-table-wrap"><table className="inventory-table"><thead><tr><th>Name</th><th>Type</th><th>Namespace</th><th>Plane</th><th>Observed state</th></tr></thead><tbody>{inventory.map((entity) => <tr key={entity.entity_id}><td><strong>{entity.name}</strong><small>{entity.entity_id}</small></td><td>{entity.entity_type.replace("kubernetes.", "")}</td><td>{entity.namespace ?? "cluster"}</td><td>{entity.plane.replaceAll("_", " ")}</td><td><code>{JSON.stringify(entity.observed_state)}</code></td></tr>)}</tbody></table></div>
              </section>
            )}

            {tab === "topology" && (
              <section className="panel">
                <div className="panel-heading"><div><span className="eyebrow">Dependency graph</span><h2>Operational topology</h2><p>Every edge retains its source and confidence. Filter without changing the underlying graph.</p></div>{topology && <Badge tone="accent">{topology.relationships.length} edges</Badge>}</div>
                {topology ? <EnvironmentTopology entities={topology.entities} relationships={topology.relationships} assessments={health} /> : <div className="empty-state large">Open or collect a snapshot to compile topology.</div>}
              </section>
            )}

            {tab === "health" && (
              <HealthWorkspace assessments={health} profiles={profiles} />
            )}

            {tab === "snapshots" && (
              <section className="panel">
                <div className="panel-heading"><div><span className="eyebrow">Immutable history</span><h2>Snapshots</h2><p>Open any prior world projection or compare it to its predecessor.</p></div></div>
                <div className="snapshot-list">
                  {snapshots.map((item) => <button type="button" key={item.snapshot_id} className={snapshot?.snapshot_id === item.snapshot_id ? "is-selected" : ""} onClick={() => void openSnapshot(item.snapshot_id)}><span><strong>{new Date(item.captured_at_iso).toLocaleString()}</strong><small>{item.snapshot_id}</small></span><span className="snapshot-stats"><Badge tone={tone(item.status)}>{item.status}</Badge><small>{item.entity_count} entities · {item.relationship_count} edges</small></span></button>)}
                  {snapshots.length === 0 && <div className="empty-state">No snapshots captured.</div>}
                </div>
                {snapshot && <div className="snapshot-inspector"><JsonInspector value={snapshot.collection_summary} /></div>}
              </section>
            )}

            {tab === "artifacts" && (
              <section className="panel">
                <div className="panel-heading"><div><span className="eyebrow">Content-addressed evidence</span><h2>Snapshot artifacts</h2></div></div>
                <ArtifactExplorer artifacts={snapshot?.artifacts ?? []} />
              </section>
            )}
          </>
        )}
      </section>
    </main>
  );
}

function DiffSummary({ diff }: { diff: SnapshotDiff }) {
  return (
    <div className="diff-workspace">
      <div className="diff-metrics">
        {Object.entries(diff.summary).map(([key, value]) => <div key={key}><span>{key.replaceAll("_", " ")}</span><strong>{value}</strong></div>)}
      </div>
      <div className="diff-changes">
        {diff.entity_changes.slice(0, 12).map((change) => (
          <div key={change.entity_id} className="diff-row"><Badge tone={change.change_type === "removed" ? "negative" : change.change_type === "added" ? "positive" : "warning"}>{change.change_type}</Badge><span><strong>{change.entity_id}</strong><small>{change.field_changes.slice(0, 3).map((item) => item.path).join(", ") || "Identity changed"}</small></span></div>
        ))}
      </div>
    </div>
  );
}

function HealthWorkspace({ assessments, profiles }: { assessments: OperationalProfileAssessment[]; profiles: OperationalProfileSpec[] }) {
  const [selectedProfile, setSelectedProfile] = useState(assessments[0]?.profile_id ?? "");
  const assessment = assessments.find((item) => item.profile_id === selectedProfile) ?? assessments[0] ?? null;
  const profile = profiles.find((item) => item.profile_id === assessment?.profile_id);
  const grouped = useMemo(() => {
    const result = new Map<string, OperationalProfileAssessment["evaluations"]>();
    for (const evaluation of assessment?.evaluations ?? []) {
      const family = evaluation.invariant_id.split(":")[0].split(".")[0];
      const items = result.get(family) ?? [];
      items.push(evaluation);
      result.set(family, items);
    }
    return result;
  }, [assessment]);

  if (!assessment) return <section className="panel"><div className="empty-state large">No operational profile assessment is available for this snapshot.</div></section>;
  return (
    <section className="panel">
      <div className="panel-heading"><div><span className="eyebrow">Contract evaluation</span><h2>Operational health</h2><p>{profile?.description ?? assessment.profile_id}</p></div><label className="field compact-control"><span>Profile</span><select value={assessment.profile_id} onChange={(event: ChangeEvent<HTMLSelectElement>) => setSelectedProfile(event.target.value)}>{assessments.map((item) => <option key={item.profile_id} value={item.profile_id}>{item.profile_id}</option>)}</select></label></div>
      <div className="health-summary"><Badge tone={tone(assessment.status)}>{assessment.status}</Badge>{Object.entries(assessment.counts).map(([key, value]) => <span key={key}>{key}: <strong>{value}</strong></span>)}</div>
      <div className="health-matrix">
        {Array.from(grouped.entries()).map(([family, evaluations]) => <div className="health-family" key={family}><div className="health-family-title"><strong>{family.replaceAll("_", " ")}</strong><span>{evaluations.length} checks</span></div>{evaluations.map((evaluation) => <div className="health-cell" key={evaluation.invariant_id}><Badge tone={tone(evaluation.status)}>{evaluation.status}</Badge><span><strong>{evaluation.invariant_id}</strong><small>{evaluation.explanation}</small></span></div>)}</div>)}
      </div>
    </section>
  );
}
