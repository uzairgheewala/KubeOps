import { useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";
import { Badge } from "../../components/Badge";
import { JsonInspector } from "../../components/JsonInspector";
import type { KnowledgePackManifest, PackCatalogResponse, PackScenarioCoverage } from "../../types";

function contributionCount(manifest: KnowledgePackManifest): number {
  return Object.values(manifest.contributions).reduce((total, value) => total + (Array.isArray(value) ? value.length : 0), 0);
}

export function PackWorkbench() {
  const [catalog, setCatalog] = useState<PackCatalogResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tab, setTab] = useState<"overview" | "contributions" | "coverage" | "manifest">("overview");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.packs().then((value) => {
      setCatalog(value);
      setSelectedId(value.packs[0]?.manifest.pack_id ?? null);
    }).catch((reason: Error) => setError(reason.message));
  }, []);

  const selected = useMemo(() => catalog?.packs.find((item) => item.manifest.pack_id === selectedId) ?? null, [catalog, selectedId]);
  if (error) return <main className="startup-error"><h1>Pack catalog unavailable</h1><p>{error}</p></main>;
  if (!catalog) return <main className="startup-loading">Resolving knowledge packs…</main>;

  return (
    <main className="pack-workbench">
      <aside className="pack-rail">
        <div className="section-heading"><div><small>Release 0.5</small><h2>Knowledge Packs</h2></div><Badge tone={catalog.resolution.blocked_pack_ids.length ? "warning" : "positive"}>{catalog.resolution.active_pack_ids.length} active</Badge></div>
        <p className="muted">Provider and component semantics resolved before they enter the operational kernel.</p>
        <div className="pack-list">
          {catalog.packs.map((item) => <button type="button" key={item.manifest.pack_id} className={selectedId === item.manifest.pack_id ? "is-selected" : ""} onClick={() => setSelectedId(item.manifest.pack_id)}>
            <span><strong>{item.manifest.title}</strong><small>{item.manifest.pack_id} · {item.manifest.version}</small></span>
            <Badge tone={item.status?.state === "active" ? "positive" : "warning"}>{item.status?.state ?? "discovered"}</Badge>
          </button>)}
        </div>
      </aside>
      <section className="pack-main">
        {selected && <>
          <header className="pack-header"><div><small>{selected.manifest.pack_kind} pack</small><h1>{selected.manifest.title}</h1><p>{selected.manifest.description}</p></div><div className="header-status"><Badge tone="accent">v{selected.manifest.version}</Badge><Badge tone={selected.status?.issues.length ? "warning" : "positive"}>{selected.status?.issues.length ?? 0} issues</Badge></div></header>
          <nav className="workspace-tabs">
            {(["overview","contributions","coverage","manifest"] as const).map((value) => <button type="button" key={value} className={tab === value ? "active" : ""} onClick={() => setTab(value)}>{value}</button>)}
          </nav>
          {tab === "overview" && <div className="workspace-grid">
            <section className="panel"><div className="section-heading"><h2>Resolution</h2></div><div className="metric-grid"><div><small>Contributions</small><strong>{contributionCount(selected.manifest)}</strong></div><div><small>Capabilities</small><strong>{selected.manifest.capabilities.length}</strong></div><div><small>Dependencies</small><strong>{selected.manifest.dependencies.length}</strong></div><div><small>Priority</small><strong>{selected.manifest.priority}</strong></div></div></section>
            <section className="panel"><div className="section-heading"><h2>Dependencies</h2></div>{selected.manifest.dependencies.length ? <div className="dependency-list">{selected.manifest.dependencies.map((item) => <article key={item.pack_id}><strong>{item.pack_id}</strong><code>{item.version_constraint}</code><Badge tone={item.optional ? "neutral" : "accent"}>{item.optional ? "optional" : "required"}</Badge></article>)}</div> : <p className="muted">No pack dependencies.</p>}</section>
            <section className="panel span-two"><div className="section-heading"><h2>Compatibility and authority</h2></div><JsonInspector value={{ compatibility: selected.manifest.compatibility, capabilities: selected.manifest.capabilities, supported_entity_types: selected.manifest.supported_entity_types, source: selected.source }} /></section>
          </div>}
          {tab === "contributions" && <section className="panel"><div className="section-heading"><h2>Contribution catalog</h2><Badge tone="accent">{contributionCount(selected.manifest)} total</Badge></div><div className="contribution-grid">{(Object.entries(selected.manifest.contributions) as Array<[string, unknown[]]>).map(([category, entries]) => <article key={category}><header><strong>{category.replaceAll("_", " ")}</strong><Badge tone={entries.length ? "accent" : "neutral"}>{entries.length}</Badge></header>{entries.length ? <JsonInspector value={entries} /> : <p className="muted">No contributions.</p>}</article>)}</div></section>}
          {tab === "coverage" && <section className="panel"><div className="section-heading"><h2>Scenario coverage</h2></div><div className="coverage-list">{(catalog.coverage.by_pack[selected.manifest.pack_id] ?? []).map((item: PackScenarioCoverage, index: number) => <article key={`${item.support_level}-${index}`}><Badge tone="accent">{item.support_level}</Badge><div><strong>{item.family_ids.join(", ") || "Generic families"}</strong><small>{item.invariant_families.join(" · ")}</small><small>{item.topology_patterns.join(" · ")}</small></div></article>)}</div></section>}
          {tab === "manifest" && <section className="panel"><div className="section-heading"><h2>Canonical manifest</h2><code>{selected.status?.manifest_hash}</code></div><JsonInspector value={selected.manifest} /></section>}
        </>}
      </section>
    </main>
  );
}
