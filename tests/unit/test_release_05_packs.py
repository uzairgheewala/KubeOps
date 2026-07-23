from __future__ import annotations

from pathlib import Path

import pytest

from kubeops_core.actions import build_builtin_action_catalog
from kubeops_core.diagnosis import build_builtin_diagnostic_catalog
from kubeops_core.discovery.normalize import normalize_entity, resource_document
from kubeops_core.lifecycle import LifecycleProfileRegistry
from kubeops_core.models import (
    EnvironmentSnapshot,
    InvariantDefinition,
    InvariantEvaluation,
    OperationalEntity,
    OperationalProfileAssessment,
    Relationship,
    TopologyGraph,
)
from kubeops_core.models.enums import HealthStatus, InvariantFamily, Severity
from kubeops_core.packs import PackManager
from kubeops_core.profiles import OperationalProfileRegistry
from kubeops_core.topology import TopologyCompiler
from kubeops_core.diagnosis.engine import HypothesisEngine
from kubeops_core.models.diagnosis import EvidenceFact, Symptom


def _manager(repo_root: Path) -> PackManager:
    manager = PackManager(kubeops_version="1.0.0", kubernetes_version="1.31.0")
    assert manager.load_directory(repo_root / "packs") == 11
    return manager


def _resource(kind: str, name: str, namespace: str = "demo", **metadata):
    payload = {
        "apiVersion": "apps/v1" if kind in {"Deployment", "StatefulSet"} else "v1",
        "kind": kind,
        "metadata": {"name": name, "namespace": namespace, **metadata},
        "spec": {"replicas": 1},
        "status": {"readyReplicas": 0, "observedGeneration": 1, "conditions": []},
    }
    document = resource_document(payload, "test", "2026-07-23T00:00:00+00:00")
    return document, normalize_entity(document)


def test_all_builtin_packs_resolve_and_cover_every_contribution_surface(repo_root: Path) -> None:
    manager = _manager(repo_root)
    resolution = manager.resolve()
    assert resolution.blocked_pack_ids == []
    assert resolution.active_pack_ids[0] == "generic-kubernetes"
    assert set(resolution.active_pack_ids) == {
        "generic-kubernetes", "docker-host", "kind", "k3s", "coredns", "ingress-nginx",
        "argocd", "postgres", "redis", "django", "celery",
    }
    counts = resolution.contribution_counts
    assert counts["entity_classifiers"] == 11
    assert counts["relationship_resolvers"] == 3
    assert counts["operational_profiles"] == 7
    assert counts["evidence_intents"] == 9
    assert counts["collectors"] == 9
    assert counts["causal_templates"] == 9
    assert counts["action_types"] == 12
    assert counts["lifecycle_profiles"] == 2
    assert counts["verification_templates"] == 3
    assert counts["redaction_rules"] == 1
    assert counts["scenario_coverage"] == 11


def test_dependency_closure_and_version_compatibility(repo_root: Path) -> None:
    manager = _manager(repo_root)
    resolution = manager.resolve(["kind"])
    assert resolution.active_pack_ids == ["generic-kubernetes", "docker-host", "kind"]

    incompatible = PackManager(kubeops_version="2.0.0")
    incompatible.load_directory(repo_root / "packs")
    issues = incompatible.validate("kind")
    assert any(item.code == "kubeops_version_incompatible" for item in issues)


def test_pack_classification_preserves_specialized_component_identity(repo_root: Path) -> None:
    runtime = _manager(repo_root).runtime()
    document, entity = _resource("Deployment", "coredns", "kube-system")
    classified = runtime.classify_entity(document, entity)
    assert classified.entity_type == "platform.coredns"
    assert {"kubernetes.deployment", "platform.coredns"}.issubset(classified.entity_type_lineage)
    assert classified.provider == "coredns"
    assert "coredns.component" in classified.capabilities
    assert classified.extensions["kubeops_pack"]["classifiers"]


def test_pack_relationship_resolver_connects_declared_application_dependency(repo_root: Path) -> None:
    runtime = _manager(repo_root).runtime()
    pg_doc, pg = _resource("Service", "postgres", annotations={})
    django_doc, django = _resource(
        "Deployment", "django-api",
        annotations={"kubeops.io/requires": "demo/postgres"},
    )
    pg = pg.model_copy(update={"entity_type": "application.postgres", "provider": "postgres"})
    django = runtime.classify_entity(django_doc, django)
    snapshot = EnvironmentSnapshot(
        snapshot_id="snapshot", environment_id="env", captured_at_iso="2026-07-23T00:00:00+00:00",
        started_at_iso="2026-07-23T00:00:00+00:00", completed_at_iso="2026-07-23T00:00:00+00:00",
        status="complete", source_type="fixture", source_fingerprint="fixture", entities=[django, pg], raw_resource_count=2,
    )
    topology = TopologyCompiler(runtime).compile_snapshot(snapshot)
    matches = [item for item in topology.relationships if item.provenance == "pack:django.declared-dependency.v1"]
    assert len(matches) == 1
    assert matches[0].source_id == django.entity_id
    assert matches[0].target_id == pg.entity_id
    assert matches[0].relationship_type == "requires_for_service"


def test_pack_contributions_merge_into_existing_catalogs(repo_root: Path) -> None:
    runtime = _manager(repo_root).runtime()
    actions = build_builtin_action_catalog(runtime)
    diagnostics = build_builtin_diagnostic_catalog(runtime)
    assert actions.get("kind.control-plane.start.v1").metadata["pack_id"] == "kind"
    assert actions.get("postgres.rollout_restart.v1").default_risk.risk_class == "R3"
    assert diagnostics.template("postgres.not_serviceable.v1").metadata["pack_id"] == "postgres"
    assert diagnostics.collector("argocd.application.snapshot.v1").supported_entity_types == {"platform.argocd"}


def test_pack_profiles_and_lifecycle_profiles_load_without_kernel_changes(repo_root: Path) -> None:
    runtime = _manager(repo_root).runtime()
    profiles = OperationalProfileRegistry()
    assert profiles.load_pack_runtime(runtime) == 7
    assert profiles.get("postgres-serviceable.v1").invariant_templates[0].selector.entity_types == {"application.postgres"}
    lifecycle = LifecycleProfileRegistry()
    assert lifecycle.load_pack_runtime(runtime) == 2
    assert lifecycle.get("kind-provider-startup.v1").stages[0].action_templates[0].action_type_id == "kind.control-plane.start.v1"


def test_component_specific_causal_template_only_applies_to_matching_entity_type(repo_root: Path) -> None:
    runtime = _manager(repo_root).runtime()
    catalog = build_builtin_diagnostic_catalog(runtime)
    symptom = Symptom(
        symptom_id="symptom", symptom_type="invariant.readiness.violated", statement="not ready",
        subject_ids=["component"], invariant_family=InvariantFamily.READINESS,
        health_status=HealthStatus.UNHEALTHY,
    )
    evidence = [EvidenceFact(
        evidence_id="fact", fact_type="invariant.violated", statement="not ready", value=False,
        subject_ids=["component"], collector_id="test", observed_at_iso="2026-07-23T00:00:00+00:00",
    )]
    postgres = OperationalEntity(entity_id="component", entity_type="application.postgres", name="postgres", plane="application")
    graph = TopologyGraph(graph_id="graph", environment_id="env", snapshot_id="snapshot", generated_at_iso="2026-07-23T00:00:00+00:00", entities=[postgres])
    hypotheses, _ = HypothesisEngine(catalog).generate([symptom], evidence, graph)
    assert any(item.family_id == "postgres.not_serviceable" for item in hypotheses)
    assert not any(item.family_id == "redis.not_serviceable" for item in hypotheses)


def test_pack_redaction_removes_component_credentials(repo_root: Path) -> None:
    runtime = _manager(repo_root).runtime()
    payload = {"spec": {"password": "secret", "nested": {"clientSecret": "sensitive"}, "safe": "ok"}}
    result = runtime.redact(payload, resource_kind="Deployment")
    assert result["spec"]["password"] == "<redacted>"
    assert result["spec"]["nested"]["clientSecret"] == "<redacted>"
    assert result["spec"]["safe"] == "ok"


def test_pack_coverage_report_preserves_support_level_and_provenance(repo_root: Path) -> None:
    report = _manager(repo_root).runtime().coverage_report()
    assert "kind.control_plane_unavailable" in report.family_support
    assert report.family_support["kind.control_plane_unavailable"][0]["pack_id"] == "kind"
    assert any(item["pack_id"] == "postgres" for item in report.invariant_support["readiness"])


def test_pack_dependency_cycle_is_rejected() -> None:
    from kubeops_core.models.pack import KnowledgePackManifest, PackDependency

    manager = PackManager(kubeops_version="0.5.0")
    manager.register(KnowledgePackManifest(pack_id="cycle-a", version="0.1.0", title="A", pack_kind="integration", dependencies=[PackDependency(pack_id="cycle-b")]))
    manager.register(KnowledgePackManifest(pack_id="cycle-b", version="0.1.0", title="B", pack_kind="integration", dependencies=[PackDependency(pack_id="cycle-a")]))
    resolution = manager.resolve(["cycle-a"])
    assert resolution.active_pack_ids == []
    assert set(resolution.blocked_pack_ids) == {"cycle-a", "cycle-b"}
    assert any(item.code == "dependency_cycle" for item in resolution.issues)


def test_cross_pack_contribution_collision_blocks_both_packs(repo_root: Path) -> None:
    from kubeops_core.models.pack import KnowledgePackManifest, PackContributions

    manager = _manager(repo_root)
    action = manager.get("kind").contributions.action_types[0]
    manager.register(
        KnowledgePackManifest(
            pack_id="colliding-pack",
            version="0.1.0",
            title="Colliding pack",
            pack_kind="integration",
            contributions=PackContributions(action_types=[action]),
        )
    )
    resolution = manager.resolve(["kind", "colliding-pack"])
    assert {"kind", "colliding-pack"}.issubset(set(resolution.blocked_pack_ids))
    collisions = [item for item in resolution.issues if item.code == "cross_pack_contribution_collision"]
    assert {item.pack_id for item in collisions} == {"kind", "colliding-pack"}
    assert all(item.contribution_id == action.action_type_id for item in collisions)


def test_pack_resolution_artifact_chain_is_complete_and_reproducible(repo_root: Path, tmp_path: Path) -> None:
    from kubeops_core.artifacts import FileArtifactStore, build_pack_artifacts

    runtime = _manager(repo_root).runtime()
    first = build_pack_artifacts(runtime.resolution, runtime.manifests, runtime.coverage_report())
    second = build_pack_artifacts(runtime.resolution, runtime.manifests, runtime.coverage_report())
    # Coverage timestamps are intentionally current observations; reuse the same
    # coverage object when asserting deterministic reconstruction.
    coverage = runtime.coverage_report()
    first = build_pack_artifacts(runtime.resolution, runtime.manifests, coverage)
    second = build_pack_artifacts(runtime.resolution, runtime.manifests, coverage)
    assert [item.content_hash for item in first] == [item.content_hash for item in second]
    assert len([item for item in first if item.artifact_type == "knowledge_pack_manifest"]) == 11
    assert first[-1].artifact_type == "pack_resolution_manifest"
    store = FileArtifactStore(tmp_path)
    paths = [store.put(item) for item in first]
    assert len(paths) == len(first)
    assert all(path.exists() for path in paths)


def test_pack_aware_fixture_preserves_generic_health_and_adds_component_semantics(repo_root: Path) -> None:
    import yaml
    from kubeops_core.environments import EnvironmentIntelligenceService
    from kubeops_core.lifecycle import LifecyclePlanner
    from kubeops_core.models import EnvironmentDefinition

    runtime = _manager(repo_root).runtime()
    environment = EnvironmentDefinition.model_validate(
        yaml.safe_load((repo_root / "environments" / "demo-pack-stack-fixture.v1.yaml").read_text(encoding="utf-8"))
    )
    # Resolve fixture paths independently of the process working directory.
    access = environment.access_methods[0].model_copy(
        update={"fixture_path": str(repo_root / str(environment.access_methods[0].fixture_path))}
    )
    environment = environment.model_copy(update={"access_methods": [access]})
    profiles = OperationalProfileRegistry()
    profiles.load_directory(repo_root / "profiles")
    profiles.load_pack_runtime(runtime)
    result = EnvironmentIntelligenceService(runtime).collect(
        environment,
        profiles=[profiles.get(profile_id) for profile_id in environment.operational_profile_ids],
    )
    assessment = {item.profile_id: item.status for item in result.assessments}
    assert str(assessment["cluster-observable.v1"]) == "healthy"
    assert str(assessment["coredns-serviceable.v1"]) == "healthy"
    assert str(assessment["postgres-serviceable.v1"]) == "healthy"
    assert str(assessment["redis-serviceable.v1"]) == "healthy"
    assert str(assessment["django-serviceable.v1"]) == "unhealthy"
    assert str(assessment["celery-serviceable.v1"]) == "unhealthy"

    entities = {item.name: item for item in result.snapshot.entities}
    assert entities["kind-control-plane"].entity_type == "provider.kind.control_plane"
    assert "kubernetes.node" in entities["kind-control-plane"].entity_type_lineage
    assert entities["django-api"].entity_type == "application.django"
    assert entities["postgres"].entity_type == "application.postgres"
    assert any(item.provenance == "pack:django.declared-dependency.v1" for item in result.topology.relationships)
    assert any(item.provenance == "pack:celery.declared-dependency.v1" for item in result.topology.relationships)

    lifecycle = LifecycleProfileRegistry()
    lifecycle.load_pack_runtime(runtime)
    plan = LifecyclePlanner(build_builtin_action_catalog(runtime)).plan(
        lifecycle.get("kind-provider-startup.v1"), result.snapshot, mode="dry_run"
    )
    assert len(plan.actions) == 1
    assert plan.actions[0].action_type_id == "kind.control-plane.start.v1"
    assert plan.actions[0].target_ids == [entities["kind-control-plane"].entity_id]


def test_conflicts_apply_to_selected_resolution_not_merely_installed_inventory() -> None:
    from kubeops_core.models.pack import KnowledgePackManifest

    manager = PackManager(kubeops_version="0.5.0")
    manager.register(KnowledgePackManifest(pack_id="primary", version="1.0.0", title="Primary", pack_kind="integration", conflicts_with={"alternative"}))
    manager.register(KnowledgePackManifest(pack_id="alternative", version="1.0.0", title="Alternative", pack_kind="integration"))
    assert manager.resolve(["primary"]).active_pack_ids == ["primary"]
    combined = manager.resolve(["primary", "alternative"])
    assert "primary" in combined.blocked_pack_ids
    assert any(item.code == "pack_conflict" for item in combined.issues)


def test_pack_cannot_silently_override_kernel_catalog_entries() -> None:
    from kubeops_core.models.pack import KnowledgePackManifest, PackContributions

    kernel_action = build_builtin_action_catalog().get("docker.container.start.v1")
    manager = PackManager(kubeops_version="0.5.0")
    manager.register(
        KnowledgePackManifest(
            pack_id="kernel-collision",
            version="1.0.0",
            title="Kernel collision",
            pack_kind="integration",
            contributions=PackContributions(action_types=[kernel_action]),
        )
    )
    runtime = manager.runtime(["kernel-collision"])
    with pytest.raises(ValueError):
        build_builtin_action_catalog(runtime)
