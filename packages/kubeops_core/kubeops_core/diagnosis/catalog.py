from __future__ import annotations

from kubeops_core.models.diagnosis import CausalTemplate, CollectorDefinition, EvidenceIntent
from kubeops_core.models.enums import InvariantFamily
from kubeops_core.registry.base import TypedRegistry


class DiagnosticCatalog:
    """Versioned extension catalog for read-only investigation semantics."""

    def __init__(self) -> None:
        self._intents: TypedRegistry[EvidenceIntent] = TypedRegistry("evidence intents")
        self._collectors: TypedRegistry[CollectorDefinition] = TypedRegistry("collectors")
        self._templates: TypedRegistry[CausalTemplate] = TypedRegistry("causal templates")

    def register_intent(self, intent: EvidenceIntent, *, replace: bool = False) -> None:
        self._intents.register(intent.intent_id, intent, replace=replace)

    def register_collector(self, collector: CollectorDefinition, *, replace: bool = False) -> None:
        self._collectors.register(collector.collector_id, collector, replace=replace)

    def register_template(self, template: CausalTemplate, *, replace: bool = False) -> None:
        self._templates.register(template.template_id, template, replace=replace)

    def intent(self, intent_id: str) -> EvidenceIntent:
        return self._intents.get(intent_id)

    def collector(self, collector_id: str) -> CollectorDefinition:
        return self._collectors.get(collector_id)

    def template(self, template_id: str) -> CausalTemplate:
        return self._templates.get(template_id)

    def intents(self) -> list[EvidenceIntent]:
        return self._intents.values()

    def collectors(self) -> list[CollectorDefinition]:
        return self._collectors.values()

    def templates(self) -> list[CausalTemplate]:
        return self._templates.values()

    def templates_for_family(self, family: InvariantFamily | str) -> list[CausalTemplate]:
        value = InvariantFamily(str(family))
        return [item for item in self.templates() if value in item.invariant_families]


_INTENTS = [
    EvidenceIntent(
        intent_id="entity.current_state.v1",
        title="Inspect current entity state",
        question="What authoritative state is currently reported for the affected entity?",
        questions_answered=["entity_exists", "entity_ready", "entity_conditions"],
        required_fact_types=["entity.exists", "entity.state"],
        preferred_collector_ids=["snapshot.entity_state.v1", "snapshot.conditions.v1"],
        stopping_condition="all_required_facts",
    ),
    EvidenceIntent(
        intent_id="dependency.path.v1",
        title="Inspect dependency path",
        question="Which dependency edges connect the affected component to its providers and consumers?",
        questions_answered=["dependency_path", "upstream_providers", "downstream_consumers"],
        required_fact_types=["topology.neighborhood"],
        preferred_collector_ids=["snapshot.topology_neighborhood.v1"],
    ),
    EvidenceIntent(
        intent_id="endpoint.layer.v1",
        title="Discriminate reachability layer",
        question="Is endpoint failure caused by resolution, route, transport, TLS, or endpoint absence?",
        questions_answered=["name_resolution", "route", "transport", "tls", "endpoint_presence"],
        required_fact_types=["endpoint.layer"],
        preferred_collector_ids=["snapshot.endpoint_state.v1"],
    ),
    EvidenceIntent(
        intent_id="identity.authentication.v1",
        title="Inspect authentication chain",
        question="Is the intended credential present, fresh, and propagated to the client request?",
        questions_answered=["credential_present", "credential_fresh", "credential_propagated"],
        required_fact_types=["authentication.state"],
        preferred_collector_ids=["snapshot.authentication_state.v1"],
    ),
    EvidenceIntent(
        intent_id="identity.authorization.v1",
        title="Inspect authorization result",
        question="Did an authenticated identity possess the bounded capability required for the operation?",
        questions_answered=["authenticated_identity", "authorization_decision", "permission_gap"],
        required_fact_types=["authorization.state"],
        preferred_collector_ids=["snapshot.authorization_state.v1", "snapshot.permission_gaps.v1"],
    ),
    EvidenceIntent(
        intent_id="controller.progress.v1",
        title="Inspect reconciliation progress",
        question="Is the responsible controller observing the current generation and making progress?",
        questions_answered=["observed_generation", "controller_conditions", "reconcile_stall"],
        required_fact_types=["controller.progress"],
        preferred_collector_ids=["snapshot.controller_progress.v1", "snapshot.conditions.v1"],
    ),
    EvidenceIntent(
        intent_id="placement.constraints.v1",
        title="Inspect placement constraints",
        question="Which capacity, taint, affinity, topology, quota, or storage constraint prevents placement?",
        questions_answered=["capacity", "taints", "affinity", "storage_topology", "quota"],
        required_fact_types=["placement.state"],
        preferred_collector_ids=["snapshot.placement_state.v1", "snapshot.discovery_issues.v1"],
    ),
    EvidenceIntent(
        intent_id="capacity.pressure.v1",
        title="Inspect capacity and pressure",
        question="Which bounded resource is below its operational safety threshold?",
        questions_answered=["cpu", "memory", "disk", "inodes", "pids", "quota"],
        required_fact_types=["capacity.state"],
        preferred_collector_ids=["snapshot.capacity_state.v1"],
    ),
    EvidenceIntent(
        intent_id="configuration.references.v1",
        title="Inspect configuration references",
        question="Do all required references resolve to intended compatible entities?",
        questions_answered=["reference_exists", "reference_target", "binding_compatibility"],
        required_fact_types=["configuration.reference_state"],
        preferred_collector_ids=["snapshot.reference_state.v1", "snapshot.topology_neighborhood.v1"],
    ),
    EvidenceIntent(
        intent_id="observability.quality.v1",
        title="Inspect evidence quality",
        question="Is required evidence present, fresh, authoritative, and mutually consistent?",
        questions_answered=["missing_evidence", "stale_evidence", "contradictory_evidence", "permission_gap"],
        required_fact_types=["observability.quality"],
        preferred_collector_ids=["snapshot.observability_quality.v1", "snapshot.permission_gaps.v1"],
    ),
]


_COLLECTORS = [
    CollectorDefinition(
        collector_id="snapshot.entity_state.v1",
        title="Snapshot entity-state collector",
        handler_id="entity_state",
        questions_answered=["entity_exists", "entity_ready", "entity_state"],
        fact_types=["entity.exists", "entity.state", "entity.ready"],
        required_inputs={"snapshot"},
        cost_class="negligible",
    ),
    CollectorDefinition(
        collector_id="snapshot.conditions.v1",
        title="Kubernetes condition collector",
        handler_id="conditions",
        questions_answered=["entity_conditions", "controller_conditions"],
        fact_types=["kubernetes.condition"],
        required_inputs={"snapshot"},
        cost_class="negligible",
    ),
    CollectorDefinition(
        collector_id="snapshot.topology_neighborhood.v1",
        title="Topology-neighborhood collector",
        handler_id="topology_neighborhood",
        questions_answered=["dependency_path", "upstream_providers", "downstream_consumers"],
        fact_types=["topology.neighborhood", "dependency.edge"],
        required_inputs={"snapshot", "topology"},
        cost_class="negligible",
    ),
    CollectorDefinition(
        collector_id="snapshot.endpoint_state.v1",
        title="Layered endpoint-state collector",
        handler_id="endpoint_state",
        questions_answered=["name_resolution", "route", "transport", "tls", "endpoint_presence"],
        fact_types=["endpoint.layer", "endpoint.reachable", "endpoint.ready"],
        required_inputs={"snapshot"},
        cost_class="low",
    ),
    CollectorDefinition(
        collector_id="snapshot.authentication_state.v1",
        title="Authentication-state collector",
        handler_id="authentication_state",
        questions_answered=["credential_present", "credential_fresh", "credential_propagated"],
        fact_types=["authentication.state", "authentication.failure"],
        required_inputs={"snapshot"},
        cost_class="low",
    ),
    CollectorDefinition(
        collector_id="snapshot.authorization_state.v1",
        title="Authorization-state collector",
        handler_id="authorization_state",
        questions_answered=["authenticated_identity", "authorization_decision"],
        fact_types=["authorization.state", "authorization.denied"],
        required_inputs={"snapshot"},
        cost_class="low",
    ),
    CollectorDefinition(
        collector_id="snapshot.controller_progress.v1",
        title="Controller-progress collector",
        handler_id="controller_progress",
        questions_answered=["observed_generation", "reconcile_stall"],
        fact_types=["controller.progress", "controller.stalled"],
        required_inputs={"snapshot"},
        cost_class="low",
    ),
    CollectorDefinition(
        collector_id="snapshot.placement_state.v1",
        title="Placement-constraint collector",
        handler_id="placement_state",
        questions_answered=["capacity", "taints", "affinity", "storage_topology", "quota"],
        fact_types=["placement.state", "placement.unsatisfied_constraint"],
        required_inputs={"snapshot"},
        cost_class="low",
    ),
    CollectorDefinition(
        collector_id="snapshot.capacity_state.v1",
        title="Capacity-state collector",
        handler_id="capacity_state",
        questions_answered=["cpu", "memory", "disk", "inodes", "pids", "quota"],
        fact_types=["capacity.state", "capacity.exhausted"],
        required_inputs={"snapshot"},
        cost_class="low",
    ),
    CollectorDefinition(
        collector_id="snapshot.reference_state.v1",
        title="Reference-resolution collector",
        handler_id="reference_state",
        questions_answered=["reference_exists", "reference_target", "binding_compatibility"],
        fact_types=["configuration.reference_state", "configuration.reference_missing"],
        required_inputs={"snapshot", "topology"},
        cost_class="low",
    ),
    CollectorDefinition(
        collector_id="snapshot.discovery_issues.v1",
        title="Discovery-issue collector",
        handler_id="discovery_issues",
        questions_answered=["collector_errors", "resource_warnings"],
        fact_types=["discovery.issue"],
        required_inputs={"snapshot"},
        cost_class="negligible",
    ),
    CollectorDefinition(
        collector_id="snapshot.permission_gaps.v1",
        title="Permission-gap collector",
        handler_id="permission_gaps",
        questions_answered=["permission_gap"],
        fact_types=["authorization.permission_gap", "observability.permission_gap"],
        required_inputs={"snapshot"},
        cost_class="negligible",
    ),
    CollectorDefinition(
        collector_id="snapshot.observability_quality.v1",
        title="Observability-quality collector",
        handler_id="observability_quality",
        questions_answered=["missing_evidence", "stale_evidence", "contradictory_evidence"],
        fact_types=["observability.quality", "observability.gap"],
        required_inputs={"snapshot"},
        cost_class="negligible",
    ),
]


_TEMPLATES = [
    CausalTemplate(
        template_id="operational.invariant_violation.v1",
        family_id="operational.invariant_violation",
        title="Operational invariant violation",
        claim_template="{subject} violates a required {family} operational contract.",
        invariant_families=set(InvariantFamily),
        supporting_fact_types={"invariant.violated"},
        predicted_fact_types={"entity.state"},
        evidence_intent_ids=["entity.current_state.v1"],
        generic=True,
    ),
    CausalTemplate(
        template_id="entity.required_absent.v1",
        family_id="entity.required_absent",
        parent_family_id="operational.invariant_violation",
        title="Required entity absent",
        claim_template="Required entity {subject} is absent from the observed environment.",
        invariant_families={InvariantFamily.EXISTENCE},
        supporting_fact_types={"entity.absent", "entity.exists.false"},
        contradicting_fact_types={"entity.exists.true"},
        predicted_fact_types={"entity.exists"},
        evidence_intent_ids=["entity.current_state.v1"],
        specificity=4,
    ),
    CausalTemplate(
        template_id="binding.invalid.v1",
        family_id="binding.invalid",
        parent_family_id="operational.invariant_violation",
        title="Reference or binding invalid",
        claim_template="A required reference or binding for {subject} does not resolve correctly.",
        invariant_families={InvariantFamily.IDENTITY_RESOLUTION, InvariantFamily.STRUCTURAL, InvariantFamily.CONFIGURATION},
        supporting_fact_types={"configuration.reference_missing", "configuration.reference_invalid"},
        contradicting_fact_types={"configuration.reference_valid"},
        predicted_fact_types={"configuration.reference_state"},
        evidence_intent_ids=["configuration.references.v1", "dependency.path.v1"],
        specificity=3,
    ),
    CausalTemplate(
        template_id="dependency.endpoint_unreachable.v1",
        family_id="dependency.endpoint_unreachable",
        parent_family_id="operational.invariant_violation",
        title="Dependency endpoint unreachable",
        claim_template="A required communication path for {subject} cannot be established.",
        invariant_families={InvariantFamily.REACHABILITY},
        supporting_fact_types={"endpoint.reachable.false", "endpoint.layer"},
        contradicting_fact_types={"endpoint.reachable.true"},
        predicted_fact_types={"endpoint.layer"},
        evidence_intent_ids=["endpoint.layer.v1", "dependency.path.v1"],
        specificity=3,
    ),
    CausalTemplate(
        template_id="dependency.authentication_failure.v1",
        family_id="dependency.authentication_failure",
        parent_family_id="operational.invariant_violation",
        title="Authentication chain failure",
        claim_template="The intended identity for {subject} is absent, expired, invalid, or not propagated.",
        invariant_families={InvariantFamily.AUTHENTICATION},
        supporting_fact_types={"authentication.failure", "authentication.state.failed"},
        contradicting_fact_types={"authentication.state.succeeded"},
        predicted_fact_types={"authentication.state"},
        evidence_intent_ids=["identity.authentication.v1", "identity.authorization.v1"],
        specificity=4,
    ),
    CausalTemplate(
        template_id="dependency.authorization_failure.v1",
        family_id="dependency.authorization_failure",
        parent_family_id="operational.invariant_violation",
        title="Authorization decision denied",
        claim_template="The authenticated identity used by {subject} lacks the required bounded capability.",
        invariant_families={InvariantFamily.AUTHORIZATION},
        supporting_fact_types={"authorization.denied", "authorization.permission_gap"},
        contradicting_fact_types={"authorization.allowed"},
        predicted_fact_types={"authorization.state"},
        evidence_intent_ids=["identity.authorization.v1", "identity.authentication.v1"],
        specificity=4,
    ),
    CausalTemplate(
        template_id="workload.no_feasible_placement.v1",
        family_id="workload.no_feasible_placement",
        parent_family_id="operational.invariant_violation",
        title="No feasible workload placement",
        claim_template="No available placement satisfies all constraints required by {subject}.",
        invariant_families={InvariantFamily.PLACEMENT},
        supporting_fact_types={"placement.unsatisfied_constraint"},
        contradicting_fact_types={"placement.feasible"},
        predicted_fact_types={"placement.state"},
        evidence_intent_ids=["placement.constraints.v1", "capacity.pressure.v1"],
        specificity=4,
    ),
    CausalTemplate(
        template_id="controller.convergence_failure.v1",
        family_id="controller.convergence_failure",
        parent_family_id="operational.invariant_violation",
        title="Controller convergence failure",
        claim_template="The responsible controller for {subject} is not converging accepted state to desired state.",
        invariant_families={InvariantFamily.LIFECYCLE_PROGRESS},
        supporting_fact_types={"controller.stalled", "controller.progress.false"},
        contradicting_fact_types={"controller.progress.true"},
        predicted_fact_types={"controller.progress"},
        evidence_intent_ids=["controller.progress.v1", "entity.current_state.v1"],
        specificity=4,
    ),
    CausalTemplate(
        template_id="component.not_serviceable.v1",
        family_id="component.not_serviceable",
        parent_family_id="operational.invariant_violation",
        title="Component not serviceable",
        claim_template="Component {subject} exists but cannot currently satisfy its service contract.",
        invariant_families={InvariantFamily.READINESS, InvariantFamily.LIVENESS},
        supporting_fact_types={"entity.ready.false", "entity.serviceable.false"},
        contradicting_fact_types={"entity.ready.true", "entity.serviceable.true"},
        predicted_fact_types={"entity.state", "topology.neighborhood", "kubernetes.condition"},
        evidence_intent_ids=["entity.current_state.v1", "dependency.path.v1"],
        specificity=2,
    ),
    CausalTemplate(
        template_id="resource.exhaustion.v1",
        family_id="resource.exhaustion",
        parent_family_id="operational.invariant_violation",
        title="Bounded resource exhausted",
        claim_template="A bounded resource required by {subject} is exhausted or below its safety threshold.",
        invariant_families={InvariantFamily.CAPACITY, InvariantFamily.PERFORMANCE},
        supporting_fact_types={"capacity.exhausted"},
        contradicting_fact_types={"capacity.sufficient"},
        predicted_fact_types={"capacity.state"},
        evidence_intent_ids=["capacity.pressure.v1", "placement.constraints.v1"],
        specificity=4,
    ),
    CausalTemplate(
        template_id="state.divergence.v1",
        family_id="state.divergence",
        parent_family_id="operational.invariant_violation",
        title="Declared and runtime state diverge",
        claim_template="Representations of required state for {subject} are inconsistent beyond allowed drift.",
        invariant_families={InvariantFamily.CONSISTENCY, InvariantFamily.FRESHNESS},
        supporting_fact_types={"state.divergence", "state.stale"},
        contradicting_fact_types={"state.consistent"},
        predicted_fact_types={"entity.state"},
        evidence_intent_ids=["entity.current_state.v1", "observability.quality.v1"],
        specificity=3,
    ),
    CausalTemplate(
        template_id="operation.idempotency_violation.v1",
        family_id="operation.idempotency_violation",
        parent_family_id="operational.invariant_violation",
        title="Operation is not idempotent",
        claim_template="Repeated execution involving {subject} does not preserve the intended bounded effect.",
        invariant_families={InvariantFamily.IDEMPOTENCY, InvariantFamily.ORDERING},
        predicted_fact_types={"entity.state"},
        evidence_intent_ids=["entity.current_state.v1"],
        specificity=2,
    ),
    CausalTemplate(
        template_id="evidence.observability_gap.v1",
        family_id="evidence.observability_gap",
        parent_family_id="operational.invariant_violation",
        title="Required evidence unavailable",
        claim_template="The state of {subject} cannot be diagnosed with the available evidence boundary.",
        invariant_families={InvariantFamily.OBSERVABILITY},
        supporting_fact_types={"observability.gap", "observability.permission_gap"},
        contradicting_fact_types={"observability.complete"},
        predicted_fact_types={"observability.quality"},
        evidence_intent_ids=["observability.quality.v1"],
        specificity=3,
    ),
]


def build_builtin_diagnostic_catalog(pack_runtime=None) -> DiagnosticCatalog:
    catalog = DiagnosticCatalog()
    for item in _INTENTS:
        catalog.register_intent(item)
    for item in _COLLECTORS:
        catalog.register_collector(item)
    for item in _TEMPLATES:
        catalog.register_template(item)
    if pack_runtime is not None:
        for item in pack_runtime.evidence_intents():
            catalog.register_intent(item)
        for item in pack_runtime.collectors():
            catalog.register_collector(item)
        for item in pack_runtime.causal_templates():
            catalog.register_template(item)
    return catalog
