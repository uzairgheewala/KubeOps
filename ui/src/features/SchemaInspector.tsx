import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { Badge } from "../components/Badge";
import { JsonInspector } from "../components/JsonInspector";
import type { RegistrySnapshot } from "../types";

const fallbackSchemaNames = [
  "OperationalEntity",
  "Relationship",
  "InvariantDefinition",
  "ScenarioFamily",
  "ScenarioInstance",
  "SimulationRun",
  "ScenarioComposition"
];

export function SchemaInspector() {
  const [schemaName, setSchemaName] = useState(fallbackSchemaNames[0]);
  const [schema, setSchema] = useState<Record<string, unknown> | null>(null);
  const [registry, setRegistry] = useState<RegistrySnapshot | null>(null);
  const [category, setCategory] = useState("all");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.registry().then(setRegistry).catch((reason: Error) => setError(reason.message));
  }, []);

  useEffect(() => {
    setError(null);
    api.schema(schemaName).then(setSchema).catch((reason: Error) => setError(reason.message));
  }, [schemaName]);

  const categories = useMemo(
    () => ["all", ...Object.keys(registry?.counts ?? {}).sort()],
    [registry]
  );
  const entries = useMemo(
    () => (registry?.entries ?? []).filter((entry) => category === "all" || entry.category === category),
    [registry, category]
  );
  const schemaNames = registry?.schemas ?? fallbackSchemaNames;

  return (
    <div className="registry-page-grid">
      <section className="workspace-section registry-section">
        <div className="section-heading">
          <div>
            <span className="eyebrow">Extension surfaces</span>
            <h2>Canonical registry</h2>
            <p>Inspect the finite operational grammar available to scenario families and packs.</p>
          </div>
          <label className="field compact-field">
            <span>Category</span>
            <select value={category} onChange={(event: React.ChangeEvent<HTMLSelectElement>) => setCategory(event.target.value)}>
              {categories.map((item) => <option key={item} value={item}>{item.replaceAll("_", " ")}</option>)}
            </select>
          </label>
        </div>
        <div className="registry-counts">
          {Object.entries(registry?.counts ?? {}).map(([name, count]) => (
            <div className="metric-card" key={name}>
              <span>{name.replaceAll("_", " ")}</span>
              <strong>{count}</strong>
              <small>registered entries</small>
            </div>
          ))}
        </div>
        <div className="registry-table-wrap">
          <table className="registry-table">
            <thead><tr><th>Category</th><th>Key</th><th>Version</th><th>Capabilities</th></tr></thead>
            <tbody>
              {entries.map((entry) => (
                <tr key={`${entry.category}:${entry.registry_key}`}>
                  <td><Badge>{entry.category}</Badge></td>
                  <td><strong>{entry.registry_key}</strong><small>{entry.description}</small></td>
                  <td>{entry.version}</td>
                  <td><div className="badge-row">{entry.capabilities.length ? entry.capabilities.map((capability) => <Badge key={capability} tone="accent">{capability}</Badge>) : <span className="muted">—</span>}</div></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="workspace-section">
        <div className="section-heading">
          <div>
            <span className="eyebrow">Canonical IR</span>
            <h2>Schema inspector</h2>
            <p>Inspect the versioned contracts shared by the simulator, API, CLI, artifacts, and UI.</p>
          </div>
          <label className="field compact-field">
            <span>Schema</span>
            <select value={schemaName} onChange={(event: React.ChangeEvent<HTMLSelectElement>) => setSchemaName(event.target.value)}>
              {schemaNames.map((name) => <option key={name}>{name}</option>)}
            </select>
          </label>
        </div>
        {error ? <div className="error-banner">{error}</div> : <JsonInspector value={schema} />}
      </section>
    </div>
  );
}
