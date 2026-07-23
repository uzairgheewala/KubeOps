from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4

from kubeops_core.models.action import ScheduledMutation, StateMutation, TransitionRule
from kubeops_core.models.composition import CompositionComponent, ScenarioComposition
from kubeops_core.models.entity import OperationalEntity
from kubeops_core.models.enums import DisturbanceMechanism, ObservationProfileKind, TemporalForm
from kubeops_core.models.invariant import InvariantDefinition
from kubeops_core.models.observation import ObservationProfile
from kubeops_core.models.predicate import Predicate
from kubeops_core.models.relationship import Relationship
from kubeops_core.models.scenario import DisturbanceDefinition, ScenarioInstance

from .compiler import ScenarioCompiler


class ScenarioComposer:
    """Compile multiple family instances into one namespaced scenario world.

    Composition is structural: each component is compiled normally, then its
    entity namespace is prefixed by a stable alias. This prevents accidental
    collisions while retaining each family's invariant and transition semantics.
    """

    def __init__(self, compiler: ScenarioCompiler) -> None:
        self.compiler = compiler

    def compose(self, spec: ScenarioComposition) -> ScenarioInstance:
        compiled: list[tuple[CompositionComponent, ScenarioInstance, int]] = []
        cursor = 0
        for index, component in enumerate(spec.components):
            if component.start_at_seconds is not None:
                offset = component.start_at_seconds
            elif spec.operator in {"sequential", "recovery_interference"}:
                offset = cursor
            else:
                offset = 0
            instance = self.compiler.compile(
                component.family_id,
                component.bindings,
                disturbance_id=component.disturbance_id,
                observation_profile_id=component.observation_profile_id,
                scenario_id=f"{spec.composition_id}:{component.alias}",
                max_time_seconds=component.duration_hint_seconds,
            )
            compiled.append((component, instance, offset))
            if spec.operator in {"sequential", "recovery_interference"}:
                cursor = offset + component.duration_hint_seconds + spec.gap_seconds

        entities: list[OperationalEntity] = []
        relationships: list[Relationship] = []
        invariants: list[InvariantDefinition] = []
        rules: list[TransitionRule] = []
        mutations: list[ScheduledMutation] = []
        hidden_ids: set[str] = set()
        hidden_paths: dict[str, set[str]] = {}
        lag_seconds: dict[str, int] = {}
        contradictions: dict[str, dict[str, Any]] = {}
        component_metadata: list[dict[str, Any]] = []

        for index, (component, instance, offset) in enumerate(compiled):
            prefix = f"{component.alias}::"
            entity_map = {entity.entity_id: f"{prefix}{entity.entity_id}" for entity in instance.entities}
            entities.extend(self._prefix_entities(instance.entities, entity_map))
            relationships.extend(self._prefix_relationships(instance.relationships, prefix, entity_map))
            invariants.extend(self._prefix_invariants(instance.invariants, prefix, entity_map))
            rules.extend(self._prefix_rules(instance.transition_rules, prefix, entity_map))

            component_mutations = self._prefix_mutations(
                instance.disturbance.mutations, prefix, entity_map, offset
            )
            if spec.operator == "conditional" and index > 0:
                assert component.activation_predicate is not None
                condition = self._rewrite_predicate(component.activation_predicate, entity_map)
                for mutation in component_mutations:
                    rules.append(
                        TransitionRule(
                            rule_id=f"{prefix}activation::{mutation.mutation_id}",
                            title=f"Conditional activation: {mutation.description}",
                            conditions=[condition],
                            effects=[mutation.mutation],
                            delay_seconds=mutation.at_seconds,
                            fire_once=True,
                        )
                    )
            else:
                mutations.extend(component_mutations)

            profile = instance.observation_profile
            if spec.operator == "masking" and component.alias in spec.masked_aliases:
                hidden_ids.update(entity_map.values())
            hidden_ids.update(entity_map[item] for item in profile.hidden_entity_ids if item in entity_map)
            for entity_id, paths in profile.hidden_paths.items():
                hidden_paths[entity_map[entity_id]] = set(paths)
            for entity_id, lag in profile.lag_seconds.items():
                lag_seconds[entity_map[entity_id]] = lag
            for entity_id, values in profile.contradictory_overrides.items():
                contradictions[entity_map[entity_id]] = deepcopy(values)

            component_metadata.append(
                {
                    "alias": component.alias,
                    "family_id": instance.family_id,
                    "scenario_id": instance.scenario_id,
                    "offset_seconds": offset,
                    "entity_map": entity_map,
                    "disturbance_id": instance.disturbance.disturbance_id,
                }
            )

        known_ids = {entity.entity_id for entity in entities}
        for relationship in spec.bridge_relationships:
            if relationship.source_id not in known_ids or relationship.target_id not in known_ids:
                raise ValueError(
                    f"bridge relationship {relationship.relationship_id} references unknown entity"
                )
            relationships.append(relationship)

        temporal_form = {
            "concurrent": TemporalForm.CONCURRENT,
            "sequential": TemporalForm.CASCADING,
            "conditional": TemporalForm.DELAYED_EFFECT,
            "masking": TemporalForm.LATENT,
            "recovery_interference": TemporalForm.RECOVERY_INDUCED,
        }[spec.operator]
        max_time = max(
            offset + component.duration_hint_seconds
            for component, _, offset in compiled
        ) + spec.gap_seconds

        return ScenarioInstance(
            scenario_id=f"composition-{uuid4().hex[:12]}",
            family_id=f"composition.{spec.operator}",
            family_version="1.0.0",
            title=spec.title,
            description=f"{spec.operator.replace('_', ' ').title()} composition of {len(compiled)} scenario families.",
            bindings={component.alias: component.bindings for component, _, _ in compiled},
            entities=entities,
            relationships=relationships,
            invariants=invariants,
            transition_rules=rules,
            disturbance=DisturbanceDefinition(
                disturbance_id=f"{spec.composition_id}.disturbance",
                title=f"Composed {spec.operator} disturbance",
                mechanism=DisturbanceMechanism.COMMISSION,
                temporal_form=temporal_form,
                mutations=sorted(mutations, key=lambda item: (item.at_seconds, item.mutation_id)),
            ),
            observation_profile=ObservationProfile(
                profile_id=f"{spec.composition_id}.observation",
                title="Composed observation profile",
                profile_kind=ObservationProfileKind.PARTIAL
                if hidden_ids or hidden_paths or lag_seconds or contradictions
                else ObservationProfileKind.FULL,
                hidden_entity_ids=hidden_ids,
                hidden_paths=hidden_paths,
                lag_seconds=lag_seconds,
                contradictory_overrides=contradictions,
            ),
            max_time_seconds=max_time,
            metadata={
                "composition": spec.model_dump(mode="json"),
                "components": component_metadata,
            },
        )

    @staticmethod
    def _prefix_entities(
        entities: list[OperationalEntity], entity_map: dict[str, str]
    ) -> list[OperationalEntity]:
        return [
            entity.model_copy(update={"entity_id": entity_map[entity.entity_id]})
            for entity in entities
        ]

    @staticmethod
    def _prefix_relationships(
        relationships: list[Relationship], prefix: str, entity_map: dict[str, str]
    ) -> list[Relationship]:
        return [
            relationship.model_copy(
                update={
                    "relationship_id": f"{prefix}{relationship.relationship_id}",
                    "source_id": entity_map[relationship.source_id],
                    "target_id": entity_map[relationship.target_id],
                }
            )
            for relationship in relationships
        ]

    def _prefix_invariants(
        self,
        invariants: list[InvariantDefinition],
        prefix: str,
        entity_map: dict[str, str],
    ) -> list[InvariantDefinition]:
        return [
            invariant.model_copy(
                update={
                    "invariant_id": f"{prefix}{invariant.invariant_id}",
                    "subject_id": entity_map[invariant.subject_id],
                    "predicate": self._rewrite_predicate(invariant.predicate, entity_map),
                }
            )
            for invariant in invariants
        ]

    def _prefix_rules(
        self,
        rules: list[TransitionRule],
        prefix: str,
        entity_map: dict[str, str],
    ) -> list[TransitionRule]:
        return [
            rule.model_copy(
                update={
                    "rule_id": f"{prefix}{rule.rule_id}",
                    "conditions": [
                        self._rewrite_predicate(condition, entity_map)
                        for condition in rule.conditions
                    ],
                    "effects": [self._rewrite_mutation(effect, entity_map) for effect in rule.effects],
                }
            )
            for rule in rules
        ]

    def _prefix_mutations(
        self,
        mutations: list[ScheduledMutation],
        prefix: str,
        entity_map: dict[str, str],
        offset: int,
    ) -> list[ScheduledMutation]:
        return [
            mutation.model_copy(
                update={
                    "mutation_id": f"{prefix}{mutation.mutation_id}",
                    "at_seconds": mutation.at_seconds + offset,
                    "mutation": self._rewrite_mutation(mutation.mutation, entity_map),
                }
            )
            for mutation in mutations
        ]

    @staticmethod
    def _rewrite_mutation(mutation: StateMutation, entity_map: dict[str, str]) -> StateMutation:
        payload = mutation.entity_payload
        if payload and "entity_id" in payload:
            payload = deepcopy(payload)
            payload["entity_id"] = entity_map.get(payload["entity_id"], payload["entity_id"])
        return mutation.model_copy(
            update={
                "entity_id": entity_map.get(mutation.entity_id, mutation.entity_id),
                "entity_payload": payload,
            }
        )

    def _rewrite_predicate(self, predicate: Predicate, entity_map: dict[str, str]) -> Predicate:
        payload = predicate.model_dump(mode="python")
        return self._rewrite_predicate_payload(payload, entity_map)

    def _rewrite_predicate_payload(self, payload: dict[str, Any], entity_map: dict[str, str]) -> Predicate:
        from pydantic import TypeAdapter

        if "entity_id" in payload:
            payload["entity_id"] = entity_map.get(payload["entity_id"], payload["entity_id"])
        if "predicates" in payload:
            payload["predicates"] = [
                self._rewrite_predicate_payload(item, entity_map).model_dump(mode="python")
                for item in payload["predicates"]
            ]
        if "predicate" in payload:
            payload["predicate"] = self._rewrite_predicate_payload(
                payload["predicate"], entity_map
            ).model_dump(mode="python")
        return TypeAdapter(Predicate).validate_python(payload)
