from __future__ import annotations

import re
from typing import Any

from kubeops_core.actions import ActionCatalog
from kubeops_core.invariants.evaluator import PredicateEvaluator
from kubeops_core.models.discovery import EnvironmentSnapshot
from kubeops_core.models.entity import OperationalEntity
from kubeops_core.models.health import OperationalProfileAssessment
from kubeops_core.models.lifecycle import LifecycleActionTemplate, LifecycleProfile
from kubeops_core.models.planning import ActionInstance, RecoveryPlan
from kubeops_core.util import utc_now_iso

_PLACEHOLDER = re.compile(r"\$\{([^}]+)\}")


def _world(snapshot: EnvironmentSnapshot) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for entity in snapshot.entities:
        result[entity.entity_id] = {
            "entity_id": entity.entity_id,
            "entity_type": entity.entity_type,
            "plane": entity.plane,
            "name": entity.name,
            "namespace": entity.namespace,
            "provider": entity.provider,
            "labels": entity.labels,
            "desired_state": entity.desired_state,
            "observed_state": entity.observed_state,
            "extensions": entity.extensions,
        }
    return result


def _matches(entity: OperationalEntity, selector: dict[str, Any]) -> bool:
    if not selector:
        return True
    for key, expected in selector.items():
        if key == "entity_id" and entity.entity_id != expected:
            return False
        if key == "entity_type" and entity.entity_type != expected:
            return False
        if key == "plane" and str(entity.plane) != expected:
            return False
        if key == "namespace" and entity.namespace != expected:
            return False
        if key == "name" and entity.name != expected:
            return False
        if key == "provider" and entity.provider != expected:
            return False
        if key == "labels":
            for label_key, label_value in expected.items():
                if entity.labels.get(label_key) != label_value:
                    return False
    return True


def _render(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: _render(item, variables) for key, item in value.items()}
    if isinstance(value, list):
        return [_render(item, variables) for item in value]
    if isinstance(value, str):
        match = _PLACEHOLDER.fullmatch(value)
        if match:
            return variables.get(match.group(1), value)
        return _PLACEHOLDER.sub(lambda item: str(variables.get(item.group(1), item.group(0))), value)
    return value


class LifecyclePlanner:
    def __init__(self, actions: ActionCatalog) -> None:
        self.actions = actions
        self.predicates = PredicateEvaluator()

    def plan(
        self,
        profile: LifecycleProfile,
        snapshot: EnvironmentSnapshot,
        assessment: OperationalProfileAssessment | None = None,
        *,
        mode: str = "dry_run",
        policy_id: str | None = None,
    ) -> RecoveryPlan:
        world = _world(snapshot)
        actions: list[ActionInstance] = []
        stage_terminal_actions: dict[str, list[str]] = {}
        unsupported: list[str] = []

        for stage in profile.stages:
            stage_actions: list[ActionInstance] = []
            external_dependencies = [
                action_id
                for dependency in stage.depends_on_stage_ids
                for action_id in stage_terminal_actions.get(dependency, [])
            ]
            for template in stage.action_templates:
                compiled = self._compile_template(template, stage.stage_id, stage.on_failure, snapshot, world)
                if not compiled and not template.optional:
                    unsupported.append(f"template {template.template_id} matched no entities")
                for action in compiled:
                    internal = [
                        candidate.action_id
                        for candidate in stage_actions
                        if candidate.metadata.get("template_id") in template.depends_on_template_ids
                    ]
                    action = action.model_copy(
                        update={"depends_on_action_ids": sorted(set([*external_dependencies, *internal]))}
                    )
                    stage_actions.append(action)
            actions.extend(stage_actions)
            stage_terminal_actions[stage.stage_id] = [
                action.action_id
                for action in stage_actions
                if not any(action.action_id in other.depends_on_action_ids for other in stage_actions)
            ] or external_dependencies

        target_ids = assessment.required_invariant_ids if assessment else []
        plan = RecoveryPlan(
            plan_id=f"plan:{profile.profile_id}:{snapshot.snapshot_id}:{snapshot.content_hash[:12]}",
            environment_id=snapshot.environment_id,
            operation_type=profile.operation_type,
            objective_id=profile.target_operational_profile_id,
            target_invariant_ids=target_ids,
            protected_invariant_ids=profile.protected_invariant_ids,
            actions=actions,
            verification_condition_ids=[
                condition.condition_id
                for stage in profile.stages
                for condition in stage.completion_conditions
            ],
            verification_conditions=[condition for stage in profile.stages for condition in stage.completion_conditions],
            mode=mode,  # type: ignore[arg-type]
            policy_id=policy_id or profile.default_policy_id,
            unsupported_assumptions=unsupported,
            created_at_iso=utc_now_iso(),
            metadata={
                "lifecycle_profile_id": profile.profile_id,
                "snapshot_id": snapshot.snapshot_id,
                "stage_count": len(profile.stages),
                "stage_order": [stage.stage_id for stage in profile.stages],
            },
        )
        return plan

    def _compile_template(
        self,
        template: LifecycleActionTemplate,
        stage_id: str,
        on_failure: str,
        snapshot: EnvironmentSnapshot,
        world: dict[str, dict[str, Any]],
    ) -> list[ActionInstance]:
        definition = self.actions.get(template.action_type_id)
        candidates = [entity for entity in snapshot.entities if _matches(entity, template.target_selector)]
        if not template.target_selector:
            candidates = [None]
        result: list[ActionInstance] = []
        for index, entity in enumerate(candidates):
            if template.apply_when and any(
                self.predicates.evaluate(predicate, world, snapshot.relationships).satisfied is not True
                for predicate in template.apply_when
            ):
                continue
            if template.skip_when and any(
                self.predicates.evaluate(predicate, world, snapshot.relationships).satisfied is True
                for predicate in template.skip_when
            ):
                continue
            variables = {
                "entity_id": entity.entity_id if entity else "environment",
                "entity_name": entity.name if entity else snapshot.environment_id,
                "namespace": entity.namespace if entity else None,
                "environment_id": snapshot.environment_id,
            }
            risk = definition.default_risk
            if template.risk_override:
                risk = risk.model_copy(update={"risk_class": template.risk_override})
            target_ids = [entity.entity_id] if entity else []
            action_id = f"action:{stage_id}:{template.template_id}:{index}:{snapshot.content_hash[:8]}"
            action = ActionInstance(
                action_id=action_id,
                action_type_id=template.action_type_id,
                title=template.title,
                target_ids=target_ids,
                parameters=_render(template.parameters, variables),
                risk=risk,
                status="proposed",
                idempotency_key=f"{snapshot.environment_id}:{template.action_type_id}:{':'.join(target_ids) or template.template_id}",
                stage_id=stage_id,
                checkpoint_before=risk.risk_class in {"R3", "R4", "R5"},
                optional=template.optional,
                metadata={"template_id": template.template_id, "on_failure": on_failure, **template.metadata},
            )
            self.actions.validate_instance(action)
            result.append(action)
        return result
