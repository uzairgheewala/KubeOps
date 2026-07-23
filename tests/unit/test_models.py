from kubeops_core.models.entity import OperationalEntity


def test_canonical_hash_is_stable() -> None:
    first = OperationalEntity(
        entity_id="api",
        entity_type="application",
        name="API",
        plane="application",
        labels={"b": "2", "a": "1"},
        observed_state={"ready": True, "replicas": 1},
    )
    second = OperationalEntity(
        entity_id="api",
        entity_type="application",
        name="API",
        plane="application",
        observed_state={"replicas": 1, "ready": True},
        labels={"a": "1", "b": "2"},
    )
    assert first.canonical_json() == second.canonical_json()
    assert first.content_hash == second.content_hash


def test_forward_compatible_diagnosis_and_recovery_ir() -> None:
    from kubeops_core.models import (
        ActionInstance,
        ActionTypeDefinition,
        DiagnosisCertificate,
        EvidenceIntent,
        ExecutionPolicy,
        Hypothesis,
        OperationalObjective,
        ProbeIntent,
        RecoveryCertificate,
        RecoveryPlan,
        RiskAssessment,
        VerificationCondition,
        VerificationResult,
    )
    from kubeops_core.models.enums import HealthStatus
    from kubeops_core.models.predicate import FieldEquals

    objective = OperationalObjective(
        objective_id="restore-service",
        title="Restore service",
        objective_type="recover",
        required_invariant_ids=["service.ready"],
    )
    intent = EvidenceIntent(intent_id="check-ready", question="Is the service ready?")
    hypothesis = Hypothesis(
        hypothesis_id="hyp-1",
        family_id="component.not_serviceable",
        claim="The component is not ready.",
        confidence=0.8,
    )
    probe = ProbeIntent(
        probe_id="probe-1",
        title="Inspect readiness",
        evidence_intent_id=intent.intent_id,
        applicable_hypothesis_ids=[hypothesis.hypothesis_id],
    )
    action_type = ActionTypeDefinition(
        action_type_id="simulation.restore_readiness",
        title="Restore readiness",
        default_risk=RiskAssessment(risk_class="R1"),
    )
    action = ActionInstance(
        action_id="action-1",
        action_type_id=action_type.action_type_id,
        target_ids=["service"],
        risk=action_type.default_risk,
    )
    policy = ExecutionPolicy(
        policy_id="local-simulation",
        title="Local simulation",
        allowed_risk_classes={"R0", "R1"},
    )
    plan = RecoveryPlan(
        plan_id="plan-1",
        objective_id=objective.objective_id,
        target_invariant_ids=objective.required_invariant_ids,
        actions=[action],
        mode="dry_run",
        policy_id=policy.policy_id,
    )
    condition = VerificationCondition(
        condition_id="verify-ready",
        title="Service is ready",
        predicate=FieldEquals(entity_id="service", path="ready", value=True),
        level="semantic_health",
    )
    result = VerificationResult(
        result_id="result-1",
        condition_id=condition.condition_id,
        status=HealthStatus.HEALTHY,
        evaluated_at_seconds=4,
        explanation="Readiness restored.",
    )
    diagnosis = DiagnosisCertificate(
        certificate_id="diagnosis-1",
        incident_id="incident-1",
        root_cause_hypothesis_ids=[hypothesis.hypothesis_id],
        status="failure_class_identified",
        confidence=0.8,
    )
    recovery = RecoveryCertificate(
        certificate_id="recovery-1",
        incident_id=diagnosis.incident_id,
        plan_id=plan.plan_id,
        status="recovered",
        restored_invariant_ids=objective.required_invariant_ids,
        verification_result_ids=[result.result_id],
    )

    for model in [objective, intent, hypothesis, probe, action_type, action, policy, plan, condition, result, diagnosis, recovery]:
        assert type(model).model_validate_json(model.model_dump_json()) == model
        assert len(model.content_hash) == 64
