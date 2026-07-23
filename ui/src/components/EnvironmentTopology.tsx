import { useMemo, useState } from "react";
import type { ChangeEvent } from "react";
import type { OperationalEntity, OperationalProfileAssessment, Relationship } from "../types";
import { Badge } from "./Badge";
import { JsonInspector } from "./JsonInspector";

const planeOrder = [
  "external",
  "host",
  "runtime",
  "control_plane",
  "node",
  "platform",
  "workload",
  "application",
  "operational_tooling"
];

function entityTone(entity: OperationalEntity, assessments: OperationalProfileAssessment[]) {
  const evaluations = assessments.flatMap((assessment) => assessment.evaluations);
  const relevant = evaluations.filter((item) => item.evidence_entity_ids.includes(entity.entity_id));
  if (relevant.some((item) => item.status === "unhealthy")) return "unhealthy";
  if (relevant.some((item) => item.status === "unknown" || item.status === "pending")) return "unknown";
  if (entity.observed_state?.ready === false || entity.observed_state?.exists === false) return "unhealthy";
  return "healthy";
}

type Props = {
  entities: OperationalEntity[];
  relationships: Relationship[];
  assessments: OperationalProfileAssessment[];
};

export function EnvironmentTopology({ entities, relationships, assessments }: Props) {
  const [search, setSearch] = useState("");
  const [namespace, setNamespace] = useState("all");
  const [plane, setPlane] = useState("all");
  const [hideHealthy, setHideHealthy] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<string | null>(null);

  const namespaces = useMemo(
    () => Array.from(new Set(entities.map((entity) => entity.namespace ?? "_cluster"))).sort(),
    [entities]
  );
  const planes = useMemo(
    () => Array.from(new Set(entities.map((entity) => entity.plane))).sort((a, b) => planeOrder.indexOf(a) - planeOrder.indexOf(b)),
    [entities]
  );
  const filtered = useMemo(() => {
    const query = search.toLowerCase();
    return entities.filter((entity) => {
      if (namespace !== "all" && (entity.namespace ?? "_cluster") !== namespace) return false;
      if (plane !== "all" && entity.plane !== plane) return false;
      if (query && !`${entity.name} ${entity.entity_type} ${entity.entity_id}`.toLowerCase().includes(query)) return false;
      if (hideHealthy && entityTone(entity, assessments) === "healthy") return false;
      return true;
    });
  }, [entities, namespace, plane, search, hideHealthy, assessments]);
  const visibleIds = new Set(filtered.map((entity) => entity.entity_id));
  const visibleRelationships = relationships.filter(
    (relationship) => visibleIds.has(relationship.source_id) && visibleIds.has(relationship.target_id)
  );

  const grouped = useMemo(() => {
    const result = new Map<string, OperationalEntity[]>();
    for (const entity of filtered) {
      const items = result.get(entity.plane) ?? [];
      items.push(entity);
      result.set(entity.plane, items);
    }
    for (const items of result.values()) items.sort((a, b) => a.name.localeCompare(b.name));
    return result;
  }, [filtered]);
  const columns = planes.filter((item) => grouped.has(item));
  const columnWidth = 230;
  const rowHeight = 100;
  const width = Math.max(720, columns.length * columnWidth + 80);
  const maxRows = Math.max(1, ...columns.map((item) => grouped.get(item)?.length ?? 0));
  const height = Math.max(380, maxRows * rowHeight + 100);
  const positions = new Map<string, [number, number]>();
  columns.forEach((column, columnIndex) => {
    (grouped.get(column) ?? []).forEach((entity, rowIndex) => {
      positions.set(entity.entity_id, [60 + columnIndex * columnWidth, 70 + rowIndex * rowHeight]);
    });
  });
  const selectedEntity = entities.find((item) => item.entity_id === selectedId) ?? null;
  const selectedRelationship = relationships.find((item) => item.relationship_id === selectedEdge) ?? null;

  return (
    <div className="environment-topology">
      <div className="topology-toolbar">
        <label className="field compact-control">
          <span>Search</span>
          <input value={search} onChange={(event: ChangeEvent<HTMLInputElement>) => setSearch(event.target.value)} placeholder="Name, type, or ID" />
        </label>
        <label className="field compact-control">
          <span>Namespace</span>
          <select value={namespace} onChange={(event: ChangeEvent<HTMLSelectElement>) => setNamespace(event.target.value)}>
            <option value="all">All namespaces</option>
            {namespaces.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        <label className="field compact-control">
          <span>Plane</span>
          <select value={plane} onChange={(event: ChangeEvent<HTMLSelectElement>) => setPlane(event.target.value)}>
            <option value="all">All planes</option>
            {planes.map((item) => <option key={item} value={item}>{item.replaceAll("_", " ")}</option>)}
          </select>
        </label>
        <label className="form-check topology-check">
          <input className="form-check-input" type="checkbox" checked={hideHealthy} onChange={(event: ChangeEvent<HTMLInputElement>) => setHideHealthy(event.target.checked)} />
          <span className="form-check-label">Hide healthy</span>
        </label>
      </div>
      <div className="topology-scroll">
        <svg className="environment-topology-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Operational environment topology">
          <defs>
            <marker id="environment-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" className="arrow-head" />
            </marker>
          </defs>
          {columns.map((column, index) => (
            <text key={column} x={60 + index * columnWidth} y={28} className="plane-label">
              {column.replaceAll("_", " ")}
            </text>
          ))}
          {visibleRelationships.map((edge) => {
            const source = positions.get(edge.source_id);
            const target = positions.get(edge.target_id);
            if (!source || !target) return null;
            const isSelected = edge.relationship_id === selectedEdge;
            return (
              <g key={edge.relationship_id} className={isSelected ? "edge-selected" : ""} onClick={() => setSelectedEdge(edge.relationship_id)}>
                <line
                  x1={source[0] + 165}
                  y1={source[1] + 35}
                  x2={target[0]}
                  y2={target[1] + 35}
                  className="topology-edge interactive-edge"
                  markerEnd="url(#environment-arrow)"
                />
                <title>{edge.relationship_type} · {edge.provenance ?? "unknown provenance"}</title>
              </g>
            );
          })}
          {filtered.map((entity) => {
            const [x, y] = positions.get(entity.entity_id) ?? [0, 0];
            const tone = entityTone(entity, assessments);
            return (
              <g
                key={entity.entity_id}
                transform={`translate(${x} ${y})`}
                className={`topology-node topology-node-${tone} ${selectedId === entity.entity_id ? "is-selected" : ""}`}
                onClick={() => { setSelectedId(entity.entity_id); setSelectedEdge(null); }}
                role="button"
              >
                <rect width="165" height="70" rx="12" />
                <text x="12" y="24" className="node-title">{entity.name}</text>
                <text x="12" y="44" className="node-subtitle">{entity.entity_type.replace("kubernetes.", "")}</text>
                <text x="12" y="59" className="node-id">{entity.namespace ?? "cluster scoped"}</text>
              </g>
            );
          })}
        </svg>
      </div>
      <div className="graph-legend">
        <Badge tone="positive">Healthy</Badge>
        <Badge tone="negative">Violated</Badge>
        <Badge tone="warning">Unknown or pending</Badge>
        <span className="muted">{filtered.length} entities · {visibleRelationships.length} visible relationships</span>
      </div>
      {(selectedEntity || selectedRelationship) && (
        <div className="selection-inspector">
          <div className="panel-heading compact">
            <div>
              <span className="eyebrow">Selection</span>
              <h2>{selectedEntity?.name ?? selectedRelationship?.relationship_type.replaceAll("_", " ")}</h2>
            </div>
            <button type="button" className="button secondary" onClick={() => { setSelectedId(null); setSelectedEdge(null); }}>Clear</button>
          </div>
          <JsonInspector value={selectedEntity ?? selectedRelationship} />
        </div>
      )}
    </div>
  );
}
