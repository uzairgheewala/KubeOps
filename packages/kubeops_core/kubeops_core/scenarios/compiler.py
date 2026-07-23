from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4

from kubeops_core.models.action import TransitionRule
from kubeops_core.models.entity import OperationalEntity
from kubeops_core.models.invariant import InvariantDefinition
from kubeops_core.models.observation import ObservationProfile
from kubeops_core.models.relationship import Relationship
from kubeops_core.models.scenario import (
    ConstraintSpec,
    DisturbanceDefinition,
    ScenarioBlueprint,
    ScenarioFamily,
    ScenarioInstance,
)
from kubeops_core.registry.scenarios import ScenarioFamilyRegistry
from kubeops_core.util import deep_merge

from .template import resolve_template


class ScenarioCompileError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


class ScenarioCompiler:
    def __init__(self, registry: ScenarioFamilyRegistry) -> None:
        self.registry = registry

    def effective_family(self, family_id: str) -> ScenarioFamily:
        """Return the inheritance-resolved family exposed to clients."""
        return self._merge_lineage(self.registry.lineage(family_id))

    def compile(
        self,
        family_id: str,
        bindings: dict[str, Any] | None = None,
        *,
        disturbance_id: str | None = None,
        observation_profile_id: str | None = None,
        scenario_id: str | None = None,
        max_time_seconds: int = 20,
    ) -> ScenarioInstance:
        lineage = self.registry.lineage(family_id)
        family = lineage[-1]
        merged = self.effective_family(family_id)
        if merged.abstract:
            raise ScenarioCompileError([f"scenario family {family_id} is abstract and cannot be compiled directly"])
        complete_bindings = self._complete_bindings(merged, bindings or {})
        errors = self._validate_bindings(merged, complete_bindings)
        if errors:
            raise ScenarioCompileError(errors)

        blueprint_payload = resolve_template(merged.blueprint.model_dump(mode="python"), complete_bindings)
        disturbance_payloads = resolve_template(merged.disturbances, complete_bindings)
        requested_disturbance = disturbance_id or merged.default_disturbance_id
        disturbance_payload = next(
            (item for item in disturbance_payloads if item["disturbance_id"] == requested_disturbance),
            None,
        )
        if disturbance_payload is None:
            raise ScenarioCompileError([f"unknown disturbance {requested_disturbance}"])

        blueprint = ScenarioBlueprint.model_validate(blueprint_payload)
        profiles = [ObservationProfile.model_validate(item) for item in blueprint.observation_profiles]
        requested_profile = observation_profile_id or merged.default_observation_profile_id
        profile = next((item for item in profiles if item.profile_id == requested_profile), None)
        if profile is None:
            raise ScenarioCompileError([f"unknown observation profile {requested_profile}"])

        return ScenarioInstance(
            scenario_id=scenario_id or f"scenario-{uuid4().hex[:12]}",
            family_id=family.family_id,
            family_version=family.version,
            title=resolve_template(family.title, complete_bindings),
            description=resolve_template(family.description, complete_bindings),
            bindings=complete_bindings,
            entities=[OperationalEntity.model_validate(item) for item in blueprint.entities],
            relationships=[Relationship.model_validate(item) for item in blueprint.relationships],
            invariants=[InvariantDefinition.model_validate(item) for item in blueprint.invariants],
            transition_rules=[TransitionRule.model_validate(item) for item in blueprint.transition_rules],
            disturbance=DisturbanceDefinition.model_validate(disturbance_payload),
            observation_profile=profile,
            max_time_seconds=max_time_seconds,
            metadata={
                "lineage": [item.family_id for item in lineage],
                "signature": family.signature.model_dump(mode="json"),
                "tags": family.tags,
            },
        )

    def _merge_lineage(self, lineage: list[ScenarioFamily]) -> ScenarioFamily:
        payload = lineage[0].model_dump(mode="python")
        for family in lineage[1:]:
            child = family.model_dump(mode="python")
            payload = self._merge_family_payload(payload, child)
        return ScenarioFamily.model_validate(payload)

    def _merge_family_payload(self, parent: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
        result = deepcopy(parent)
        scalar_fields = [
            "family_id",
            "version",
            "title",
            "description",
            "parent_family_id",
            "abstract",
            "default_disturbance_id",
            "default_observation_profile_id",
        ]
        for field in scalar_fields:
            if child.get(field) is not None:
                result[field] = deepcopy(child[field])

        result["parameters"] = self._merge_named(parent.get("parameters", []), child.get("parameters", []), "name")
        result["constraints"] = parent.get("constraints", []) + child.get("constraints", [])
        result["signature"] = deep_merge(parent.get("signature", {}), child.get("signature", {}))
        result["blueprint"] = self._merge_blueprints(parent.get("blueprint", {}), child.get("blueprint", {}))
        result["disturbances"] = self._merge_named(
            parent.get("disturbances", []), child.get("disturbances", []), "disturbance_id"
        )
        result["tags"] = sorted(set(parent.get("tags", [])) | set(child.get("tags", [])))
        return result

    def _merge_blueprints(self, parent: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
        keys = {
            "entities": "entity_id",
            "relationships": "relationship_id",
            "invariants": "invariant_id",
            "transition_rules": "rule_id",
            "observation_profiles": "profile_id",
        }
        result: dict[str, Any] = {}
        for field, identity in keys.items():
            result[field] = self._merge_named(parent.get(field, []), child.get(field, []), identity)
        return result

    @staticmethod
    def _merge_named(parent: list[dict[str, Any]], child: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
        merged = {item[key]: deepcopy(item) for item in parent}
        for item in child:
            identity = item[key]
            merged[identity] = deep_merge(merged.get(identity, {}), item)
        return [merged[name] for name in sorted(merged)]

    def _complete_bindings(self, family: ScenarioFamily, supplied: dict[str, Any]) -> dict[str, Any]:
        result = deepcopy(supplied)
        for parameter in family.parameters:
            if parameter.name not in result and parameter.default is not None:
                result[parameter.name] = deepcopy(parameter.default)
        return result

    def _validate_bindings(self, family: ScenarioFamily, bindings: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        parameters = {parameter.name: parameter for parameter in family.parameters}
        unknown = sorted(set(bindings) - set(parameters))
        if unknown:
            errors.append(f"unknown bindings: {', '.join(unknown)}")
        for parameter in family.parameters:
            if parameter.required and parameter.name not in bindings:
                errors.append(f"missing required binding {parameter.name}")
                continue
            if parameter.name not in bindings:
                continue
            value = bindings[parameter.name]
            if parameter.parameter_type == "integer" and not isinstance(value, int):
                errors.append(f"binding {parameter.name} must be an integer")
            elif parameter.parameter_type == "boolean" and not isinstance(value, bool):
                errors.append(f"binding {parameter.name} must be a boolean")
            elif parameter.parameter_type == "string" and not isinstance(value, str):
                errors.append(f"binding {parameter.name} must be a string")
            elif parameter.parameter_type == "enum" and value not in parameter.options:
                errors.append(f"binding {parameter.name} must be one of {parameter.options}")
        for constraint in family.constraints:
            errors.extend(self._evaluate_constraint(constraint, bindings))
        return errors

    @staticmethod
    def _evaluate_constraint(constraint: ConstraintSpec, bindings: dict[str, Any]) -> list[str]:
        if constraint.constraint_type == "required":
            if any(name not in bindings or bindings[name] in (None, "") for name in constraint.parameters):
                return [constraint.message]
        elif constraint.constraint_type == "not_equal":
            values = [bindings.get(name) for name in constraint.parameters]
            if len(values) >= 2 and len(set(map(str, values))) != len(values):
                return [constraint.message]
        elif constraint.constraint_type == "one_of":
            if any(bindings.get(name) not in constraint.values for name in constraint.parameters):
                return [constraint.message]
        return []
