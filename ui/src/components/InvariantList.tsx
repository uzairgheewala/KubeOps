import type { InvariantDefinition, InvariantEvaluation } from "../types";
import { Badge } from "./Badge";

function tone(status: string) {
  if (status === "healthy") return "positive" as const;
  if (status === "unhealthy") return "negative" as const;
  if (status === "pending") return "warning" as const;
  return "neutral" as const;
}

export function InvariantList({
  definitions,
  evaluations,
  selected,
  onSelect
}: {
  definitions: InvariantDefinition[];
  evaluations: InvariantEvaluation[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const definitionMap = new Map(definitions.map((item) => [item.invariant_id, item]));
  return (
    <div className="invariant-list">
      {evaluations.map((evaluation) => {
        const definition = definitionMap.get(evaluation.invariant_id);
        return (
          <button
            type="button"
            className={`invariant-row ${selected === evaluation.invariant_id ? "is-selected" : ""}`}
            key={evaluation.invariant_id}
            onClick={() => onSelect(evaluation.invariant_id)}
          >
            <div>
              <strong>{definition?.title ?? evaluation.invariant_id}</strong>
              <small>{definition?.family ?? "invariant"} · {definition?.subject_id}</small>
            </div>
            <Badge tone={tone(evaluation.status)}>{evaluation.status}</Badge>
            <p>{evaluation.explanation}</p>
          </button>
        );
      })}
    </div>
  );
}
