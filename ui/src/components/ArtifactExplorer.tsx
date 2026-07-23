import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ArtifactDetail, ArtifactSummary } from "../types";
import { Badge } from "./Badge";
import { JsonInspector } from "./JsonInspector";

export function ArtifactExplorer({ artifacts }: { artifacts: ArtifactSummary[] }) {
  const [selectedId, setSelectedId] = useState<string | null>(artifacts[0]?.artifact_id ?? null);
  const [detail, setDetail] = useState<ArtifactDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSelectedId(artifacts[0]?.artifact_id ?? null);
  }, [artifacts]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    setError(null);
    api.artifact(selectedId).then(setDetail).catch((reason: Error) => setError(reason.message));
  }, [selectedId]);

  if (artifacts.length === 0) {
    return <div className="empty-state">Artifacts are emitted after a persisted simulation run.</div>;
  }

  return (
    <div className="artifact-explorer">
      <div className="artifact-list">
        {artifacts.map((artifact) => (
          <button
            type="button"
            key={artifact.artifact_id}
            className={selectedId === artifact.artifact_id ? "is-selected" : ""}
            onClick={() => setSelectedId(artifact.artifact_id)}
          >
            <span>
              <strong>{artifact.artifact_type.replaceAll("_", " ")}</strong>
              <small>{artifact.artifact_id}</small>
            </span>
            <Badge>{artifact.content_hash.slice(0, 10)}</Badge>
          </button>
        ))}
      </div>
      <div className="artifact-detail">
        {error ? <div className="error-banner">{error}</div> : (
          <>
            {detail && (
              <div className="artifact-meta">
                <Badge tone="accent">{detail.media_type}</Badge>
                <span>SHA-256 {detail.content_hash}</span>
                <span>{detail.derived_from.length} parent artifacts</span>
              </div>
            )}
            <JsonInspector value={detail?.payload} emptyLabel="Loading artifact…" />
          </>
        )}
      </div>
    </div>
  );
}
