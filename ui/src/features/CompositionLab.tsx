import { useMemo, useState } from "react";
import { api } from "../api/client";
import { ArtifactExplorer } from "../components/ArtifactExplorer";
import { Badge } from "../components/Badge";
import { InvariantList } from "../components/InvariantList";
import { Timeline } from "../components/Timeline";
import { TopologyGraph } from "../components/TopologyGraph";
import type { ScenarioFamily, SimulationRun } from "../types";

function defaults(family: ScenarioFamily) {
  return Object.fromEntries(
    family.parameters
      .filter((parameter) => parameter.default !== null && parameter.default !== undefined)
      .map((parameter) => [parameter.name, parameter.default])
  );
}

export function CompositionLab({ families }: { families: ScenarioFamily[] }) {
  const [firstId, setFirstId] = useState(families[0]?.family_id ?? "");
  const [secondId, setSecondId] = useState(families[1]?.family_id ?? families[0]?.family_id ?? "");
  const [operator, setOperator] = useState<"concurrent" | "sequential" | "recovery_interference">("concurrent");
  const [run, setRun] = useState<SimulationRun | null>(null);
  const [snapshotIndex, setSnapshotIndex] = useState(0);
  const [selectedEntity, setSelectedEntity] = useState<string | null>(null);
  const [selectedInvariant, setSelectedInvariant] = useState<string | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const first = useMemo(() => families.find((item) => item.family_id === firstId) ?? families[0], [families, firstId]);
  const second = useMemo(() => families.find((item) => item.family_id === secondId) ?? families[0], [families, secondId]);

  const execute = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await api.runComposition({
        schema_version: "kubeops.io/v1",
        composition_id: "ui-composition",
        title: `${first.title} + ${second.title}`,
        operator,
        gap_seconds: 1,
        components: [
          {
            schema_version: "kubeops.io/v1",
            alias: "first",
            family_id: first.family_id,
            bindings: defaults(first),
            disturbance_id: first.default_disturbance_id,
            observation_profile_id: first.default_observation_profile_id,
            duration_hint_seconds: 8
          },
          {
            schema_version: "kubeops.io/v1",
            alias: "second",
            family_id: second.family_id,
            bindings: defaults(second),
            disturbance_id: second.default_disturbance_id,
            observation_profile_id: second.default_observation_profile_id,
            duration_hint_seconds: 8
          }
        ],
        bridge_relationships: [],
        metadata: { source: "composition_lab" }
      });
      setRun(result);
      setSnapshotIndex(0);
      setSelectedEntity(null);
      setSelectedInvariant(null);
      setSelectedEvent(null);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const snapshot = run?.snapshots[snapshotIndex];
  const evaluations = snapshot?.invariant_evaluations ?? [];
  const selectedEvaluation = evaluations.find((item) => item.invariant_id === selectedInvariant);

  const onEventSelect = (sequence: number) => {
    setSelectedEvent(sequence);
    const candidateIndex = run?.snapshots.findIndex((item) => item.trigger_event_sequence === sequence) ?? -1;
    if (candidateIndex >= 0) setSnapshotIndex(candidateIndex);
  };

  return (
    <div className="composition-page">
      <section className="composition-controls panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">Scenario composition</span>
            <h2>Combine independent family semantics</h2>
            <p>Namespace and execute two family instances inside one deterministic operational world.</p>
          </div>
          <Badge tone="accent">simulation only</Badge>
        </div>
        <div className="composition-form">
          <label className="field">
            <span>First family</span>
            <select value={firstId} onChange={(event: React.ChangeEvent<HTMLSelectElement>) => setFirstId(event.target.value)}>
              {families.map((family) => <option key={family.family_id} value={family.family_id}>{family.family_id}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Operator</span>
            <select value={operator} onChange={(event: React.ChangeEvent<HTMLSelectElement>) => setOperator(event.target.value as typeof operator)}>
              <option value="concurrent">Concurrent</option>
              <option value="sequential">Sequential</option>
              <option value="recovery_interference">Recovery interference</option>
            </select>
          </label>
          <label className="field">
            <span>Second family</span>
            <select value={secondId} onChange={(event: React.ChangeEvent<HTMLSelectElement>) => setSecondId(event.target.value)}>
              {families.map((family) => <option key={family.family_id} value={family.family_id}>{family.family_id}</option>)}
            </select>
          </label>
          <button className="button primary composition-run" type="button" onClick={execute} disabled={busy}>
            {busy ? "Composing…" : "Compile and run"}
          </button>
        </div>
        {error && <div className="error-banner">{error}</div>}
      </section>

      <div className="metric-strip composition-metrics">
        <div className="metric-card"><span>Operator</span><strong>{operator.replaceAll("_", " ")}</strong><small>Composition semantics</small></div>
        <div className="metric-card"><span>Entities</span><strong>{run?.scenario.entities.length ?? 0}</strong><small>Namespaced world</small></div>
        <div className="metric-card"><span>Events</span><strong>{run?.timeline.length ?? 0}</strong><small>{run?.snapshots.length ?? 0} snapshots</small></div>
        <div className="metric-card"><span>Violations</span><strong>{run?.final_summary.unhealthy_invariants.length ?? 0}</strong><small>{run?.final_summary.unknown_invariants.length ?? 0} unknown</small></div>
      </div>

      <section className="panel graph-panel">
        <div className="panel-heading compact">
          <div><span className="eyebrow">Composed topology</span><h2>{run?.scenario.title ?? "Run a composition"}</h2></div>
        </div>
        {run && snapshot ? (
          <>
            <TopologyGraph
              entities={run.scenario.entities}
              relationships={run.scenario.relationships}
              state={snapshot.observed_state}
              selectedId={selectedEntity}
              onSelect={setSelectedEntity}
              affectedEntityIds={selectedEvaluation?.evidence_entity_ids ?? []}
            />
            <div className="playback">
              <button type="button" onClick={() => setSnapshotIndex(Math.max(0, snapshotIndex - 1))} disabled={snapshotIndex === 0}>← Previous</button>
              <input type="range" min={0} max={run.snapshots.length - 1} value={snapshotIndex} onChange={(event: React.ChangeEvent<HTMLInputElement>) => setSnapshotIndex(Number(event.target.value))} />
              <span>Snapshot {snapshotIndex + 1}/{run.snapshots.length} · t+{snapshot.at_seconds}s</span>
              <button type="button" onClick={() => setSnapshotIndex(Math.min(run.snapshots.length - 1, snapshotIndex + 1))} disabled={snapshotIndex === run.snapshots.length - 1}>Next →</button>
            </div>
          </>
        ) : <div className="empty-state large">Choose two families and execute the composition.</div>}
      </section>

      <div className="two-column">
        <section className="panel">
          <div className="panel-heading compact"><div><span className="eyebrow">Combined contracts</span><h2>Invariant evaluations</h2></div></div>
          {run && snapshot ? (
            <InvariantList definitions={run.scenario.invariants} evaluations={evaluations} selected={selectedInvariant} onSelect={setSelectedInvariant} />
          ) : <div className="empty-state">No composed run yet.</div>}
        </section>
        <section className="panel">
          <div className="panel-heading compact"><div><span className="eyebrow">Interleaving</span><h2>Event timeline</h2></div></div>
          <Timeline events={run?.timeline ?? []} selectedSequence={selectedEvent} onSelect={onEventSelect} />
        </section>
      </div>
      {run && (
        <section className="panel inspector-panel">
          <div className="panel-heading compact"><div><span className="eyebrow">Immutable run bundle</span><h2>Artifact explorer</h2></div><Badge>{run.artifacts.length} artifacts</Badge></div>
          <ArtifactExplorer artifacts={run.artifacts} />
        </section>
      )}
    </div>
  );
}
