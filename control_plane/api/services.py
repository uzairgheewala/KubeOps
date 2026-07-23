from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from django.conf import settings

from kubeops_core.artifacts import FileArtifactStore
from kubeops_core.actions import build_builtin_action_catalog
from kubeops_core.execution import FileOperationStore, OperationRuntime, build_default_executor_registry
from kubeops_core.lifecycle import LifecyclePlanner, LifecycleProfileRegistry
from kubeops_core.policy import ExecutionPolicyRegistry
from kubeops_core.environments import EnvironmentIntelligenceService
from kubeops_core.diagnosis import InvestigationService, ScenarioDiagnosisEvaluator, build_builtin_diagnostic_catalog
from kubeops_core.models.registry import RegistryEntry
from kubeops_core.packs import PackManager
from kubeops_core.profiles import OperationalProfileRegistry
from kubeops_core.registry import ScenarioFamilyRegistry, build_builtin_catalog
from kubeops_core.scenarios import ScenarioCompiler
from kubeops_core.simulator import SimulationEngine




@lru_cache(maxsize=1)
def pack_manager() -> PackManager:
    manager = PackManager(kubeops_version="0.5.0")
    manager.load_directory(settings.KUBEOPS_PACK_DIR)
    return manager


@lru_cache(maxsize=1)
def pack_runtime():
    requested = settings.KUBEOPS_ENABLED_PACKS or None
    return pack_manager().runtime(requested)


@lru_cache(maxsize=1)
def lifecycle_registry() -> LifecycleProfileRegistry:
    registry = LifecycleProfileRegistry()
    registry.load_directory(settings.KUBEOPS_LIFECYCLE_DIR)
    registry.load_pack_runtime(pack_runtime())
    return registry


@lru_cache(maxsize=1)
def policy_registry() -> ExecutionPolicyRegistry:
    registry = ExecutionPolicyRegistry()
    registry.load_directory(settings.KUBEOPS_POLICY_DIR)
    return registry


@lru_cache(maxsize=1)
def action_catalog():
    return build_builtin_action_catalog(pack_runtime())


@lru_cache(maxsize=1)
def lifecycle_planner() -> LifecyclePlanner:
    return LifecyclePlanner(action_catalog())


@lru_cache(maxsize=1)
def operation_store() -> FileOperationStore:
    return FileOperationStore(settings.KUBEOPS_OPERATION_DIR)


@lru_cache(maxsize=1)
def operation_runtime() -> OperationRuntime:
    return OperationRuntime(action_catalog(), build_default_executor_registry(), operation_store())


@lru_cache(maxsize=1)
def scenario_registry() -> ScenarioFamilyRegistry:
    registry = ScenarioFamilyRegistry()
    registry.load_directory(Path(settings.KUBEOPS_SCENARIO_DIR) / "families")
    return registry


@lru_cache(maxsize=1)
def profile_registry() -> OperationalProfileRegistry:
    registry = OperationalProfileRegistry()
    registry.load_directory(settings.KUBEOPS_PROFILE_DIR)
    registry.load_pack_runtime(pack_runtime())
    return registry


@lru_cache(maxsize=1)
def registry_catalog():
    catalog = build_builtin_catalog()
    for family in scenario_registry().values():
        catalog.register(
            RegistryEntry(
                registry_key=family.family_id,
                category="scenario_family",
                version=family.version,
                title=family.title,
                description=family.description,
                capabilities={"compile"} if not family.abstract else {"inherit"},
                metadata={
                    "parent_family_id": family.parent_family_id,
                    "abstract": family.abstract,
                    "content_hash": family.content_hash,
                },
            )
        )
    for profile in profile_registry().values():
        catalog.register(
            RegistryEntry(
                registry_key=profile.profile_id,
                category="operational_profile",
                version=profile.version,
                title=profile.title,
                description=profile.description,
                capabilities={"compile", "evaluate"},
                metadata={
                    "environment_classes": sorted(profile.environment_classes),
                    "template_count": len(profile.invariant_templates),
                    "content_hash": profile.content_hash,
                },
            )
        )
    for intent in diagnostic_catalog().intents():
        catalog.register(
            RegistryEntry(
                registry_key=intent.intent_id,
                category="evidence_intent",
                title=intent.title or intent.question,
                description=intent.question,
                capabilities={"plan", "collect"},
                metadata={"risk_class": intent.risk_class, "required_fact_types": intent.required_fact_types},
            )
        )
    for collector in diagnostic_catalog().collectors():
        catalog.register(
            RegistryEntry(
                registry_key=collector.collector_id,
                category="collector",
                title=collector.title,
                description=collector.description,
                capabilities={"read_only", *collector.supported_modes},
                metadata={"risk_class": collector.risk_class, "fact_types": collector.fact_types},
            )
        )
    for template in diagnostic_catalog().templates():
        catalog.register(
            RegistryEntry(
                registry_key=template.template_id,
                category="causal_template",
                title=template.title,
                description=template.claim_template,
                capabilities={"classify", "explain"},
                metadata={"family_id": template.family_id, "parent_family_id": template.parent_family_id, "specificity": template.specificity},
            )
        )
    for action in action_catalog().values():
        catalog.register(RegistryEntry(registry_key=action.action_type_id, category="action_type", title=action.title, description=action.description, capabilities={"plan", "execute"}, metadata={"risk_class": action.default_risk.risk_class, "executor_id": action.executor_id, "supported_modes": sorted(action.supported_modes)}))
    for profile in lifecycle_registry().values():
        catalog.register(RegistryEntry(registry_key=profile.profile_id, category="lifecycle_profile", version=profile.version, title=profile.title, description=profile.description, capabilities={"plan"}, metadata={"operation_type": profile.operation_type, "stage_count": len(profile.stages)}))
    for policy in policy_registry().values():
        catalog.register(RegistryEntry(registry_key=policy.policy_id, category="execution_policy", title=policy.title, capabilities={"authorize"}, metadata={"allowed_risk_classes": sorted(policy.allowed_risk_classes), "mutation_budget": policy.mutation_budget}))
    runtime = pack_runtime()
    for manifest in runtime.manifests:
        catalog.register(RegistryEntry(registry_key=manifest.pack_id, category="knowledge_pack", version=manifest.version, title=manifest.title, description=manifest.description, capabilities=set(manifest.capabilities), metadata={"pack_kind": manifest.pack_kind, "contribution_counts": manifest.contributions.counts(), "content_hash": manifest.content_hash}))
    for classifier in runtime.entity_classifiers():
        catalog.register(RegistryEntry(registry_key=classifier.classifier_id, category="entity_classifier", title=classifier.classifier_id, capabilities={"classify"}, metadata={"pack_id": classifier.extension_values.get("pack_id") or None}))
    for resolver in runtime.relationship_resolvers():
        catalog.register(RegistryEntry(registry_key=resolver.resolver_id, category="relationship_resolver", title=resolver.resolver_id, capabilities={"resolve"}, metadata={"handler_id": resolver.handler_id}))
    for template in runtime.verification_templates():
        catalog.register(RegistryEntry(registry_key=template.condition_id, category="verification_template", title=template.title, capabilities={"verify"}, metadata={"level": template.level}))
    for rule in runtime.redaction_rules():
        catalog.register(RegistryEntry(registry_key=rule.rule_id, category="redaction_rule", title=rule.rule_id, capabilities={"redact"}, metadata={"rationale": rule.rationale}))
    for manifest in runtime.manifests:
        for index, coverage in enumerate(manifest.contributions.scenario_coverage):
            catalog.register(RegistryEntry(
                registry_key=f"{manifest.pack_id}:coverage:{index}",
                category="pack_coverage",
                title=f"{manifest.title} scenario coverage {index + 1}",
                capabilities={coverage.support_level},
                metadata={"pack_id": manifest.pack_id, **coverage.model_dump(mode="json")},
            ))
    return catalog


@lru_cache(maxsize=1)
def scenario_compiler() -> ScenarioCompiler:
    return ScenarioCompiler(scenario_registry())


@lru_cache(maxsize=1)
def simulation_engine() -> SimulationEngine:
    return SimulationEngine()


@lru_cache(maxsize=1)
def diagnostic_catalog():
    return build_builtin_diagnostic_catalog(pack_runtime())


@lru_cache(maxsize=1)
def investigation_service() -> InvestigationService:
    return InvestigationService(diagnostic_catalog())


@lru_cache(maxsize=1)
def scenario_diagnosis_evaluator() -> ScenarioDiagnosisEvaluator:
    return ScenarioDiagnosisEvaluator(diagnostic_catalog())


@lru_cache(maxsize=1)
def environment_intelligence() -> EnvironmentIntelligenceService:
    return EnvironmentIntelligenceService(pack_runtime())


@lru_cache(maxsize=1)
def artifact_store() -> FileArtifactStore:
    return FileArtifactStore(settings.KUBEOPS_ARTIFACT_DIR)


def clear_service_caches() -> None:
    pack_manager.cache_clear()
    pack_runtime.cache_clear()
    lifecycle_registry.cache_clear()
    policy_registry.cache_clear()
    action_catalog.cache_clear()
    lifecycle_planner.cache_clear()
    operation_store.cache_clear()
    operation_runtime.cache_clear()
    scenario_registry.cache_clear()
    profile_registry.cache_clear()
    scenario_compiler.cache_clear()
    registry_catalog.cache_clear()
    simulation_engine.cache_clear()
    diagnostic_catalog.cache_clear()
    investigation_service.cache_clear()
    scenario_diagnosis_evaluator.cache_clear()
    environment_intelligence.cache_clear()
    artifact_store.cache_clear()
