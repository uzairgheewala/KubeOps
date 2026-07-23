import type { OperationalEntity, Relationship } from "../types";
import { Badge } from "./Badge";

const positions = [
  [130, 110],
  [390, 110],
  [650, 110],
  [260, 290],
  [520, 290],
  [130, 470],
  [390, 470],
  [650, 470]
];

function entityState(
  entityId: string,
  state: Record<string, Record<string, unknown>>,
  selectedInvariantSubjects: Set<string>
) {
  const entity = state[entityId];
  if (!entity) return "unknown";
  const observed = (entity.observed_state ?? {}) as Record<string, unknown>;
  if (observed.exists === false || observed.serviceable === false || observed.ready === false) return "unhealthy";
  if (selectedInvariantSubjects.has(entityId)) return "affected";
  return "healthy";
}

type Props = {
  entities: OperationalEntity[];
  relationships: Relationship[];
  state: Record<string, Record<string, unknown>>;
  selectedId: string | null;
  onSelect: (id: string) => void;
  affectedEntityIds?: string[];
};

export function TopologyGraph({
  entities,
  relationships,
  state,
  selectedId,
  onSelect,
  affectedEntityIds = []
}: Props) {
  const selectedInvariantSubjects = new Set(affectedEntityIds);
  const layout = new Map(
    entities.map((entity, index) => [entity.entity_id, positions[index % positions.length]])
  );

  return (
    <div className="topology-wrap">
      <svg className="topology-svg" viewBox="0 0 780 580" role="img" aria-label="Scenario topology">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" className="arrow-head" />
          </marker>
        </defs>
        {relationships.map((edge) => {
          const source = layout.get(edge.source_id);
          const target = layout.get(edge.target_id);
          if (!source || !target) return null;
          return (
            <g key={edge.relationship_id}>
              <line
                x1={source[0]}
                y1={source[1]}
                x2={target[0]}
                y2={target[1]}
                className="topology-edge"
                markerEnd="url(#arrow)"
              />
              <text
                x={(source[0] + target[0]) / 2}
                y={(source[1] + target[1]) / 2 - 10}
                className="edge-label"
                textAnchor="middle"
              >
                {edge.relationship_type.replaceAll("_", " ")}
              </text>
            </g>
          );
        })}
        {entities.map((entity) => {
          const position = layout.get(entity.entity_id)!;
          const status = entityState(entity.entity_id, state, selectedInvariantSubjects);
          return (
            <g
              key={entity.entity_id}
              className={`topology-node topology-node-${status} ${selectedId === entity.entity_id ? "is-selected" : ""}`}
              transform={`translate(${position[0] - 88} ${position[1] - 44})`}
              onClick={() => onSelect(entity.entity_id)}
              role="button"
            >
              <rect width="176" height="88" rx="14" />
              <text x="14" y="28" className="node-title">{entity.name}</text>
              <text x="14" y="50" className="node-subtitle">{entity.entity_type}</text>
              <text x="14" y="70" className="node-id">{entity.entity_id}</text>
            </g>
          );
        })}
      </svg>
      <div className="graph-legend">
        <Badge tone="positive">Healthy</Badge>
        <Badge tone="negative">Violated state</Badge>
        <Badge tone="warning">Affected invariant</Badge>
        <Badge>Unobserved</Badge>
      </div>
    </div>
  );
}
