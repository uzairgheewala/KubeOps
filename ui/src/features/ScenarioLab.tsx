import { useEffect, useMemo, useState } from "react";
import type { ChangeEvent } from "react";
import { api } from "../api/client";
import { ArtifactExplorer } from "../components/ArtifactExplorer";
import { Badge } from "../components/Badge";
import { InvariantList } from "../components/InvariantList";
import { JsonInspector } from "../components/JsonInspector";
import { Timeline } from "../components/Timeline";
import { TopologyGraph } from "../components/TopologyGraph";
import type {
  DiagnosticCaseResult,
  InvariantEvaluation,
  ScenarioFamily,
  ScenarioInstance,
  SimulationRun,
  Snapshot
} from "../types";

function defaultBindings(family: ScenarioFamily): Record<string, unknown> {
  return Object.fromEntries(
    family.parameters
      .filter((parameter) => parameter.default !== null && parameter.default !== undefined)
      .map((parameter) => [parameter.name, parameter.default])
  );
}

function familyObservationProfiles(family: ScenarioFamily) {
  const profiles = family.blueprint.observation_profiles ?? [];
  if (profiles.length > 0) return profiles;
  return [{ profile_id: family.default_observation_profile_id, title: family.default_observation_profile_id }];
}

export function ScenarioLab({ families }: { families: ScenarioFamily[] }) {
  const [familyId, setFamilyId] = useState(families[0]?.family_id ?? "");
  const family = useMemo(() => families.find((item) => item.family_id === familyId) ?? families[0], [families, familyId]);
  const [bindings, setBindings] = useState<Record<string, unknown>>({});
  const [disturbanceId, setDisturbanceId] = useState("");
  const [profileId, setProfileId] = useState("");
  const [scenario, setScenario] = useState<ScenarioInstance | null>(null);
  const [run, setRun] = useState<SimulationRun | null>(null);
  const [diagnostic, setDiagnostic] = useState<DiagnosticCaseResult | null>(null);
  const [snapshotIndex, setSnapshotIndex] = useState(0);
  const [viewMode, setViewMode] = useState<"observed" | "truth">("observed");
  const [selectedEntity, setSelectedEntity] = useState<string | null>(null);
  const [selectedInvariant, setSelectedInvariant] = useState<string | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<number | null>(null);
  const [busy, setBusy] = useState<"compile" | "run" | "diagnose" | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!family) return;
    setBindings(defaultBindings(family));
    setDisturbanceId(family.default_disturbance_id);
    setProfileId(family.default_observation_profile_id);
    setScenario(null);
    setRun(null);
    setDiagnostic(null);
    setSnapshotIndex(0);
    setSelectedEntity(null);
    setSelectedInvariant(null);
    setSelectedEvent(null);
    setError(null);
  }, [family?.family_id]);

  if (!family) return <div className="empty-state">No scenario families are registered.</div>;

  const payload = {
    family_id: family.family_id,
    bindings,
    disturbance_id: disturbanceId,
    observation_profile_id: profileId,
    max_time_seconds: 20
  };

  const compile = async () => {
    setBusy("compile");
    setError(null);
    try {
      const result = await api.compile(payload);
      setScenario(result);
      setRun(null);
      setDiagnostic(null);
      setSnapshotIndex(0);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const execute = async () => {
    setBusy("run");
    setError(null);
    try {
      const result = await api.run(payload);
      setScenario(result.scenario);
      setRun(result);
      setDiagnostic(null);
      setSnapshotIndex(0);
      setSelectedEvent(null);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const diagnose = async () => {
    setBusy("diagnose");
    setError(null);
    try {
      const expectedFamily = family.family_id.replace(/\.v\d+$/, "");
      const result = await api.diagnoseScenario({
        ...payload,
        expectation: {
          expected_family_ids: [expectedFamily],
          acceptable_parent_family_ids: ["operational.invariant_violation"],
          required_statuses: [
            "root_cause_identified",
            "failure_class_identified",
            "multiple_plausible_causes",
            "insufficient_evidence"
          ],
          maximum_probe_count: 8
        }
      });
      setDiagnostic(result);
      if (result.run) {
        setRun(result.run);
        setScenario(result.scenario ?? result.run.scenario);
        setSnapshotIndex(Math.max(0, result.run.snapshots.length - 1));
      }
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const snapshot: Snapshot | null = run?.snapshots[snapshotIndex] ?? null;
  const state = snapshot
    ? viewMode === "truth"
      ? snapshot.truth_state
      : snapshot.observed_state
    : Object.fromEntries((scenario?.entities ?? []).map((entity) => [entity.entity_id, entity]));
  const evaluations: InvariantEvaluation[] = snapshot?.invariant_evaluations ?? [];
  const selectedDefinition = scenario?.invariants.find((item) => item.invariant_id === selectedInvariant);
  const selectedEvaluation = evaluations.find((item) => item.invariant_id === selectedInvariant);
  const selectedEntityValue = selectedEntity ? state[selectedEntity] : null;
  const selectedEventValue = run?.timeline.find((item) => item.sequence === selectedEvent) ?? null;
  const affectedEntityIds = selectedEvaluation?.evidence_entity_ids ?? [];

  const onEventSelect = (sequence: number) => {
    setSelectedEvent(sequence);
    const candidateIndex = run?.snapshots.findIndex((item) => item.trigger_event_sequence === sequence) ?? -1;
    if (candidateIndex >= 0) setSnapshotIndex(candidateIndex);
  };

  return (
    <div className="lab-layout">
      <aside className="control-rail">
        <div className="rail-heading">
          <span className="eyebrow">Scenario compiler</span>
          <h2>Family bindings</h2>
          <p>Bind a generic failure family to a concrete simulated topology.</p>
        </div>

        <label className="field">
          <span>Scenario family</span>
          <select value={family.family_id} onChange={(event: ChangeEvent<HTMLSelectElement>) => setFamilyId(event.target.value)}>
            {families.map((item) => (
              <option key={item.family_id} value={item.family_id}>{item.family_id}</option>
            ))}
          </select>
        </label>

        <div className="family-summary">
          <h3>{family.title}</h3>
          <p>{family.description}</p>
          <div className="badge-row">
            {family.signature.invariant_families.map((item) => <Badge key={item} tone="accent">{item}</Badge>)}
            {family.signature.disturbance_mechanisms.map((item) => <Badge key={item}>{item}</Badge>)}
          </div>
          <small>Lineage: {family.lineage.join(" → ")}</small>
        </div>

        <div className="field-grid">
          {family.parameters.map((parameter) => {
            const value = bindings[parameter.name];
            if (parameter.parameter_type === "boolean") {
              return (
                <label className="switch-field" key={parameter.name}>
                  <input
                    type="checkbox"
                    checked={Boolean(value)}
                    onChange={(event: ChangeEvent<HTMLInputElement>) => setBindings({ ...bindings, [parameter.name]: event.target.checked })}
                  />
                  <span>{parameter.title}</span>
                </label>
              );
            }
            if (parameter.parameter_type === "enum") {
              return (
                <label className="field" key={parameter.name}>
                  <span>{parameter.title}</span>
                  <select
                    value={String(value ?? "")}
                    onChange={(event: ChangeEvent<HTMLSelectElement>) => setBindings({ ...bindings, [parameter.name]: event.target.value })}
                  >
                    {parameter.options.map((option) => (
                      <option key={String(option)} value={String(option)}>{String(option)}</option>
                    ))}
                  </select>
                </label>
              );
            }
            return (
              <label className="field" key={parameter.name}>
                <span>{parameter.title}</span>
                <input
                  type={parameter.parameter_type === "integer" ? "number" : "text"}
                  value={String(value ?? "")}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => setBindings({
                    ...bindings,
                    [parameter.name]: parameter.parameter_type === "integer"
                      ? Number(event.target.value)
                      : event.target.value
                  })}
                />
              </label>
            );
          })}
        </div>

        <label className="field">
          <span>Disturbance</span>
          <select value={disturbanceId} onChange={(event: ChangeEvent<HTMLSelectElement>) => setDisturbanceId(event.target.value)}>
            {family.disturbances.map((item) => (
              <option key={item.disturbance_id} value={item.disturbance_id}>{item.title}</option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>Observation profile</span>
          <select value={profileId} onChange={(event: ChangeEvent<HTMLSelectElement>) => setProfileId(event.target.value)}>
            {familyObservationProfiles(family).map((item) => (
              <option key={item.profile_id} value={item.profile_id}>{item.title}</option>
            ))}
          </select>
        </label>

        <div className="button-stack">
          <button type="button" className="button secondary" onClick={compile} disabled={busy !== null}>
            {busy === "compile" ? "Compiling…" : "Compile scenario"}
          </button>
          <button type="button" className="button primary" onClick={execute} disabled={busy !== null}>
            {busy === "run" ? "Running…" : "Run simulation"}
          </button>
          <button type="button" className="button secondary" onClick={diagnose} disabled={busy !== null}>
            {busy === "diagnose" ? "Diagnosing…" : "Run diagnostic evaluation"}
          </button>
        </div>
        {error && <div className="error-banner">{error}</div>}
      </aside>

      <main className="lab-main">
        <div className="metric-strip">
          <div className="metric-card">
            <span>Mode</span>
            <strong>Simulation</strong>
            <small>No live cluster authority</small>
          </div>
          <div className="metric-card">
            <span>Family</span>
            <strong>{family.family_id.split(".").slice(0, 2).join(".")}</strong>
            <small>v{family.version}</small>
          </div>
          <div className="metric-card">
            <span>Events</span>
            <strong>{run?.final_summary.event_count ?? 0}</strong>
            <small>{run ? `${run.final_summary.snapshot_count} snapshots` : "Not yet executed"}</small>
          </div>
          <div className="metric-card">
            <span>Final violations</span>
            <strong>{run?.final_summary.unhealthy_invariants.length ?? 0}</strong>
            <small>{run?.final_summary.unknown_invariants.length ?? 0} unknown</small>
          </div>
        </div>

        <section className="panel graph-panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">Operational graph</span>
              <h2>{scenario?.title ?? "Compile a scenario to inspect its topology"}</h2>
            </div>
            <div className="segmented-control" aria-label="State perspective">
              <button type="button" className={viewMode === "observed" ? "active" : ""} onClick={() => setViewMode("observed")}>Observed</button>
              <button type="button" className={viewMode === "truth" ? "active" : ""} onClick={() => setViewMode("truth")}>World truth</button>
            </div>
          </div>
          {scenario ? (
            <TopologyGraph
              entities={scenario.entities}
              relationships={scenario.relationships}
              state={state}
              selectedId={selectedEntity}
              onSelect={setSelectedEntity}
              affectedEntityIds={affectedEntityIds}
            />
          ) : (
            <div className="empty-state large">Choose bindings and compile the selected family.</div>
          )}
          {run && (
            <div className="playback">
              <button type="button" onClick={() => setSnapshotIndex(Math.max(0, snapshotIndex - 1))} disabled={snapshotIndex === 0}>← Previous</button>
              <input
                aria-label="Simulation snapshot"
                type="range"
                min={0}
                max={Math.max(0, run.snapshots.length - 1)}
                value={snapshotIndex}
                onChange={(event: ChangeEvent<HTMLInputElement>) => setSnapshotIndex(Number(event.target.value))}
              />
              <span>Snapshot {snapshotIndex + 1}/{run.snapshots.length} · t+{snapshot?.at_seconds ?? 0}s</span>
              <button type="button" onClick={() => setSnapshotIndex(Math.min(run.snapshots.length - 1, snapshotIndex + 1))} disabled={snapshotIndex >= run.snapshots.length - 1}>Next →</button>
            </div>
          )}
        </section>

        <div className="two-column">
          <section className="panel">
            <div className="panel-heading compact">
              <div>
                <span className="eyebrow">Health contracts</span>
                <h2>Invariant evaluations</h2>
              </div>
            </div>
            {scenario && evaluations.length > 0 ? (
              <InvariantList
                definitions={scenario.invariants}
                evaluations={evaluations}
                selected={selectedInvariant}
                onSelect={setSelectedInvariant}
              />
            ) : (
              <div className="empty-state">Run the scenario to evaluate observed invariants.</div>
            )}
          </section>

          <section className="panel">
            <div className="panel-heading compact">
              <div>
                <span className="eyebrow">Temporal model</span>
                <h2>Event timeline</h2>
              </div>
            </div>
            <Timeline events={run?.timeline ?? []} selectedSequence={selectedEvent} onSelect={onEventSelect} />
          </section>
        </div>

        {diagnostic && (
          <section className="panel diagnostic-evaluation-panel">
            <div className="panel-heading compact">
              <div>
                <span className="eyebrow">Scenario Lab v2</span>
                <h2>Diagnostic evaluation</h2>
              </div>
              <Badge tone={diagnostic.passed ? "positive" : "warning"}>
                {diagnostic.passed ? "expectation matched" : "expectation mismatch"}
              </Badge>
            </div>
            <div className="diagnostic-evaluation-grid">
              <div>
                <span className="muted-label">Certificate status</span>
                <strong>{diagnostic.certificate_status.replaceAll("_", " ")}</strong>
              </div>
              <div>
                <span className="muted-label">Predicted families</span>
                <div className="badge-row">
                  {diagnostic.predicted_family_ids.map((item) => <Badge key={item} tone="accent">{item}</Badge>)}
                </div>
              </div>
              <div>
                <span className="muted-label">Evidence efficiency</span>
                <strong>{diagnostic.probe_count} recommended probes</strong>
              </div>
              <div>
                <span className="muted-label">Precision / recall</span>
                <strong>{diagnostic.metrics.precision ?? 0} / {diagnostic.metrics.recall ?? 0}</strong>
              </div>
            </div>
            {diagnostic.failures.length > 0 && (
              <div className="error-banner">{diagnostic.failures.join(" · ")}</div>
            )}
            <details>
              <summary>Inspect generated incident and certificate</summary>
              <JsonInspector value={diagnostic.incident} />
            </details>
          </section>
        )}

        {run && (
          <section className="panel inspector-panel">
            <div className="panel-heading compact">
              <div><span className="eyebrow">Immutable run bundle</span><h2>Artifact explorer</h2></div>
              <Badge>{run.artifacts.length} artifacts</Badge>
            </div>
            <ArtifactExplorer artifacts={run.artifacts} />
          </section>
        )}

        <section className="panel inspector-panel">
          <div className="panel-heading compact">
            <div>
              <span className="eyebrow">Provenance</span>
              <h2>Selected object</h2>
            </div>
            <div className="badge-row">
              {selectedEntity && <Badge tone="accent">entity</Badge>}
              {selectedInvariant && <Badge tone="warning">invariant</Badge>}
              {selectedEvent !== null && <Badge>event</Badge>}
            </div>
          </div>
          <JsonInspector value={
            selectedEventValue
              ? selectedEventValue
              : selectedDefinition || selectedEvaluation
                ? { definition: selectedDefinition, evaluation: selectedEvaluation }
                : selectedEntityValue
          } />
        </section>
      </main>
    </div>
  );
}
