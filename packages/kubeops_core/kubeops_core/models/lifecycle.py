from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import Field, model_validator

from .base import SchemaModel
from .planning import RiskClass
from .predicate import Predicate
from .verification import VerificationCondition


class LifecycleActionTemplate(SchemaModel):
    kind: ClassVar[str] = "LifecycleActionTemplate"

    template_id: str
    action_type_id: str
    title: str
    target_selector: dict[str, Any] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    depends_on_template_ids: list[str] = Field(default_factory=list)
    apply_when: list[Predicate] = Field(default_factory=list)
    skip_when: list[Predicate] = Field(default_factory=list)
    risk_override: RiskClass | None = None
    optional: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class LifecycleStageDefinition(SchemaModel):
    kind: ClassVar[str] = "LifecycleStageDefinition"

    stage_id: str
    title: str
    description: str = ""
    depends_on_stage_ids: list[str] = Field(default_factory=list)
    action_templates: list[LifecycleActionTemplate] = Field(default_factory=list)
    entry_conditions: list[Predicate] = Field(default_factory=list)
    completion_conditions: list[VerificationCondition] = Field(default_factory=list)
    allow_parallel_actions: bool = False
    timeout_seconds: int = Field(default=300, ge=1)
    on_failure: Literal["stop", "pause", "rollback", "continue"] = "stop"


class LifecycleProfile(SchemaModel):
    kind: ClassVar[str] = "LifecycleProfile"

    profile_id: str
    version: str = "1.0.0"
    title: str
    description: str = ""
    operation_type: Literal["startup", "shutdown", "maintenance"]
    environment_classes: set[str] = Field(default_factory=set)
    target_operational_profile_id: str
    stages: list[LifecycleStageDefinition]
    protected_invariant_ids: list[str] = Field(default_factory=list)
    default_policy_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_graph(self) -> "LifecycleProfile":
        ids = {stage.stage_id for stage in self.stages}
        if len(ids) != len(self.stages):
            raise ValueError("lifecycle stage ids must be unique")
        stage_dependencies: dict[str, set[str]] = {}
        for stage in self.stages:
            unknown = set(stage.depends_on_stage_ids) - ids
            if unknown:
                raise ValueError(f"stage {stage.stage_id} depends on unknown stages: {sorted(unknown)}")
            if stage.stage_id in stage.depends_on_stage_ids:
                raise ValueError(f"stage {stage.stage_id} cannot depend on itself")
            stage_dependencies[stage.stage_id] = set(stage.depends_on_stage_ids)

            template_ids = {item.template_id for item in stage.action_templates}
            template_dependencies: dict[str, set[str]] = {}
            if len(template_ids) != len(stage.action_templates):
                raise ValueError(f"action template ids must be unique within stage {stage.stage_id}")
            for item in stage.action_templates:
                unknown_templates = set(item.depends_on_template_ids) - template_ids
                if unknown_templates:
                    raise ValueError(
                        f"template {item.template_id} depends on unknown templates in stage {stage.stage_id}: "
                        f"{sorted(unknown_templates)}"
                    )
                if item.template_id in item.depends_on_template_ids:
                    raise ValueError(f"template {item.template_id} cannot depend on itself")
                template_dependencies[item.template_id] = set(item.depends_on_template_ids)
            self._assert_acyclic(template_dependencies, f"action-template graph in stage {stage.stage_id}")

        self._assert_acyclic(stage_dependencies, "lifecycle stage graph")
        return self

    @staticmethod
    def _assert_acyclic(dependencies: dict[str, set[str]], label: str) -> None:
        remaining = {node: set(values) for node, values in dependencies.items()}
        ready = [node for node, values in remaining.items() if not values]
        visited: set[str] = set()
        while ready:
            node = ready.pop()
            if node in visited:
                continue
            visited.add(node)
            for candidate, values in remaining.items():
                values.discard(node)
                if not values and candidate not in visited:
                    ready.append(candidate)
        if len(visited) != len(remaining):
            raise ValueError(f"{label} must be acyclic")
