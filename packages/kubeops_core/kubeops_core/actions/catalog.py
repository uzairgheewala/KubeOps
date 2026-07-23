from __future__ import annotations

from kubeops_core.models.planning import ActionTypeDefinition, RiskAssessment
from kubeops_core.registry.base import TypedRegistry


class ActionCatalog:
    def __init__(self) -> None:
        self._actions: TypedRegistry[ActionTypeDefinition] = TypedRegistry("action catalog")

    def register(self, definition: ActionTypeDefinition, *, replace: bool = False) -> None:
        self._actions.register(definition.action_type_id, definition, replace=replace)

    def get(self, action_type_id: str) -> ActionTypeDefinition:
        return self._actions.get(action_type_id)

    def values(self) -> list[ActionTypeDefinition]:
        return self._actions.values()

    def validate_instance(self, action) -> ActionTypeDefinition:
        definition = self.get(action.action_type_id)
        schema = definition.parameter_schema or {}
        required = schema.get("required", [])
        missing = [name for name in required if name not in action.parameters]
        if missing:
            raise ValueError(
                f"action {action.action_id} is missing required parameters: {sorted(missing)}"
            )
        properties = schema.get("properties", {})
        for name, property_schema in properties.items():
            if name not in action.parameters:
                continue
            value = action.parameters[name]
            if "const" in property_schema and value != property_schema["const"]:
                raise ValueError(
                    f"action {action.action_id} parameter {name!r} must equal {property_schema['const']!r}"
                )
            expected_type = property_schema.get("type")
            if expected_type == "array" and not isinstance(value, list):
                raise ValueError(f"action {action.action_id} parameter {name!r} must be an array")
            if expected_type == "string" and not isinstance(value, str):
                raise ValueError(f"action {action.action_id} parameter {name!r} must be a string")
            if expected_type == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
                raise ValueError(f"action {action.action_id} parameter {name!r} must be an integer")
            if expected_type == "boolean" and not isinstance(value, bool):
                raise ValueError(f"action {action.action_id} parameter {name!r} must be a boolean")
        return definition

    def __len__(self) -> int:
        return len(self._actions)


def build_builtin_action_catalog() -> ActionCatalog:
    catalog = ActionCatalog()
    definitions = [
        ActionTypeDefinition(
            action_type_id="operation.wait_for_condition.v1",
            title="Wait for condition",
            description="Wait until a declared verification condition holds.",
            executor_id="builtin.wait",
            supported_modes={"simulation", "fixture", "live"},
            required_capabilities={"observe"},
            default_risk=RiskAssessment(risk_class="R0", blast_radius="none"),
            timeout_seconds=300,
            max_attempts=1,
        ),
        ActionTypeDefinition(
            action_type_id="local.process.start.v1",
            title="Start local process",
            executor_id="local.process",
            supported_modes={"simulation", "live"},
            parameter_schema={"required": ["argv"], "properties": {"argv": {"type": "array"}}},
            required_capabilities={"host.process.start"},
            expected_effects=["process_running"],
            possible_side_effects=["host_resource_consumption"],
            default_risk=RiskAssessment(risk_class="R1", blast_radius="single_process", reversible=True, idempotent=True),
            rollback_action_type_id="local.process.stop.v1",
        ),
        ActionTypeDefinition(
            action_type_id="local.process.stop.v1",
            title="Stop tracked local process",
            executor_id="local.process",
            supported_modes={"simulation", "live"},
            required_capabilities={"host.process.stop"},
            expected_effects=["process_stopped"],
            default_risk=RiskAssessment(risk_class="R1", blast_radius="single_process", availability_risk="bounded", reversible=True, idempotent=True),
        ),
        ActionTypeDefinition(
            action_type_id="docker.container.start.v1",
            title="Start Docker container",
            executor_id="docker.cli",
            supported_modes={"simulation", "live"},
            parameter_schema={"required": ["container"]},
            required_capabilities={"docker.container.start"},
            expected_effects=["container_running"],
            default_risk=RiskAssessment(risk_class="R1", blast_radius="single_container", reversible=True, idempotent=True),
            rollback_action_type_id="docker.container.stop.v1",
        ),
        ActionTypeDefinition(
            action_type_id="docker.container.stop.v1",
            title="Stop Docker container",
            executor_id="docker.cli",
            supported_modes={"simulation", "live"},
            parameter_schema={"required": ["container"]},
            required_capabilities={"docker.container.stop"},
            expected_effects=["container_stopped"],
            default_risk=RiskAssessment(risk_class="R1", blast_radius="single_container", availability_risk="bounded", reversible=True, idempotent=True),
            rollback_action_type_id="docker.container.start.v1",
        ),
        ActionTypeDefinition(
            action_type_id="host.service.restart.v1",
            title="Restart host service",
            executor_id="host.service",
            supported_modes={"simulation", "live"},
            parameter_schema={"required": ["service"]},
            required_capabilities={"host.service.restart"},
            expected_effects=["service_running"],
            possible_side_effects=["temporary_service_unavailability"],
            default_risk=RiskAssessment(risk_class="R2", blast_radius="single_host_service", availability_risk="temporary", reversible=False, idempotent=False),
        ),
        ActionTypeDefinition(
            action_type_id="kubernetes.workload.rollout_restart.v1",
            title="Restart Kubernetes workload",
            executor_id="kubectl.safe",
            supported_modes={"simulation", "live"},
            parameter_schema={"required": ["kind", "name", "namespace"]},
            required_capabilities={"kubernetes.workload.restart"},
            expected_effects=["new_workload_revision_started"],
            possible_side_effects=["temporary_capacity_reduction", "cold_start"],
            default_risk=RiskAssessment(risk_class="R2", blast_radius="single_workload", availability_risk="temporary", reversible=False, idempotent=False),
        ),
        ActionTypeDefinition(
            action_type_id="kubernetes.job.delete_terminal.v1",
            title="Delete terminal Kubernetes Job",
            executor_id="kubectl.safe",
            supported_modes={"simulation", "live"},
            parameter_schema={"required": ["name", "namespace"], "properties": {"require_terminal": {"const": True}}},
            required_capabilities={"kubernetes.job.delete_terminal"},
            expected_effects=["job_absent"],
            default_risk=RiskAssessment(risk_class="R1", blast_radius="single_ephemeral_job", data_risk="none", reversible=False, idempotent=True),
        ),
        ActionTypeDefinition(
            action_type_id="argocd.application.refresh.v1",
            title="Refresh Argo CD application",
            executor_id="kubectl.safe",
            supported_modes={"simulation", "live"},
            parameter_schema={"required": ["name", "namespace"]},
            required_capabilities={"argocd.application.refresh"},
            expected_effects=["gitops_observation_refreshed"],
            default_risk=RiskAssessment(risk_class="R1", blast_radius="single_application", reversible=True, idempotent=True),
        ),
        ActionTypeDefinition(
            action_type_id="port_forward.ensure.v1",
            title="Ensure port-forward",
            executor_id="port_forward",
            supported_modes={"simulation", "live"},
            parameter_schema={"required": ["resource", "local_port", "remote_port", "namespace"]},
            required_capabilities={"kubernetes.port_forward"},
            expected_effects=["port_forward_active"],
            default_risk=RiskAssessment(risk_class="R1", blast_radius="local_process", security_risk="local_port_exposure", reversible=True, idempotent=True),
            rollback_action_type_id="local.process.stop.v1",
        ),
    ]
    for definition in definitions:
        catalog.register(definition)
    return catalog
