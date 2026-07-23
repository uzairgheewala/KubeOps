import { useEffect, useState } from "react";
import { api } from "./api/client";
import { Badge } from "./components/Badge";
import { CompositionLab } from "./features/CompositionLab";
import { EnvironmentWorkbench } from "./features/environments/EnvironmentWorkbench";
import { ScenarioLab } from "./features/ScenarioLab";
import { SchemaInspector } from "./features/SchemaInspector";
import type { ScenarioFamily, SystemStatus } from "./types";
import "./styles.css";

type View = "environments" | "lab" | "composition" | "schemas";

export default function App() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [families, setFamilies] = useState<ScenarioFamily[]>([]);
  const [view, setView] = useState<View>("environments");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.status(), api.families()])
      .then(([nextStatus, nextFamilies]) => {
        setStatus(nextStatus);
        setFamilies(nextFamilies.filter((family) => !family.abstract));
      })
      .catch((reason: Error) => setError(reason.message));
  }, []);

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand">
          <div className="brand-mark">K</div>
          <div>
            <strong>KubeOps</strong>
            <small>Operational intelligence workbench</small>
          </div>
        </div>
        <nav className="main-nav" aria-label="Primary">
          <button type="button" className={view === "environments" ? "active" : ""} onClick={() => setView("environments")}>Environments</button>
          <button type="button" className={view === "lab" ? "active" : ""} onClick={() => setView("lab")}>Scenario Lab</button>
          <button type="button" className={view === "composition" ? "active" : ""} onClick={() => setView("composition")}>Composition Lab</button>
          <button type="button" className={view === "schemas" ? "active" : ""} onClick={() => setView("schemas")}>Canonical IR</button>
        </nav>
        <div className="header-status">
          <Badge tone={status?.status === "ok" ? "positive" : "warning"}>{status?.status ?? "connecting"}</Badge>
          <Badge tone="accent">{status?.mode ?? "read only"}</Badge>
          <span>Release {status?.release ?? "0.2.0"}</span>
          {status?.environment_count !== undefined && <span>{status.environment_count} environments</span>}
        </div>
      </header>

      {error ? (
        <main className="startup-error">
          <h1>Control plane unavailable</h1>
          <p>{error}</p>
          <code>python control_plane/manage.py runserver</code>
        </main>
      ) : !status || families.length === 0 ? (
        <main className="startup-loading">Loading operational registries…</main>
      ) : view === "environments" ? (
        <EnvironmentWorkbench />
      ) : view === "lab" ? (
        <ScenarioLab families={families} />
      ) : view === "composition" ? (
        <CompositionLab families={families} />
      ) : (
        <main className="schema-page"><SchemaInspector /></main>
      )}
    </div>
  );
}
