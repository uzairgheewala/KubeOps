from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import typer
import yaml
from rich.console import Console
from rich.table import Table

from kubeops_core.artifacts import FileArtifactStore, build_incident_artifacts, build_operation_artifacts, build_run_artifacts
from kubeops_core.actions import build_builtin_action_catalog
from kubeops_core.execution import ExecutionContext, FileOperationStore, OperationRuntime, RuntimeContext, build_default_executor_registry
from kubeops_core.lifecycle import LifecyclePlanner, LifecycleProfileRegistry
from kubeops_core.policy import ExecutionPolicyRegistry, PolicyContext
from kubeops_core.util import utc_now_iso
from kubeops_core.models.composition import ScenarioComposition
from kubeops_core.discovery import diff_snapshots
from kubeops_core.diagnosis import InvestigationService, ScenarioDiagnosisEvaluator, build_builtin_diagnostic_catalog
from kubeops_core.environments import EnvironmentIntelligenceService
from kubeops_core.health import HealthAssessmentEngine
from kubeops_core.models import ApprovalRecord, DiagnosticExpectation, EnvironmentDefinition, EnvironmentSnapshot, IncidentInvestigation, OperationRun, RecoveryPlan
from kubeops_core.profiles import OperationalProfileRegistry
from kubeops_core.models.registry import RegistryEntry
from kubeops_core.registry import ScenarioFamilyRegistry, build_builtin_catalog
from kubeops_core.scenarios import ScenarioCompileError, ScenarioCompiler, ScenarioComposer
from kubeops_core.simulator import SimulationEngine

app = typer.Typer(no_args_is_help=True, help="KubeOps Release 0.4 guarded lifecycle, recovery, diagnosis, and scenario CLI.")
family_app = typer.Typer(no_args_is_help=True, help="Inspect scenario families.")
scenario_app = typer.Typer(no_args_is_help=True, help="Compile and execute scenarios.")
composition_app = typer.Typer(no_args_is_help=True, help="Compile and execute scenario compositions.")
registry_app = typer.Typer(no_args_is_help=True, help="Inspect canonical extension registries.")
environment_app = typer.Typer(no_args_is_help=True, help="Validate environment access definitions.")
snapshot_app = typer.Typer(no_args_is_help=True, help="Collect, inspect, and compare read-only snapshots.")
profile_app = typer.Typer(no_args_is_help=True, help="Inspect and evaluate operational profiles.")
incident_app = typer.Typer(no_args_is_help=True, help="Open and refine read-only incident investigations.")
diagnostic_app = typer.Typer(no_args_is_help=True, help="Inspect diagnostic intents, collectors, and causal templates.")
lifecycle_app = typer.Typer(no_args_is_help=True, help="Plan startup and shutdown lifecycle transitions.")
policy_app = typer.Typer(no_args_is_help=True, help="Inspect execution policies and typed actions.")
operation_app = typer.Typer(no_args_is_help=True, help="Create, approve, execute, resume, and inspect durable operations.")
app.add_typer(family_app, name="family")
app.add_typer(scenario_app, name="scenario")
app.add_typer(composition_app, name="composition")
app.add_typer(registry_app, name="registry")
app.add_typer(environment_app, name="environment")
app.add_typer(snapshot_app, name="snapshot")
app.add_typer(profile_app, name="profile")
app.add_typer(incident_app, name="incident")
app.add_typer(diagnostic_app, name="diagnostic")
app.add_typer(lifecycle_app, name="lifecycle")
app.add_typer(policy_app, name="policy")
app.add_typer(operation_app, name="operation")
console = Console()


def _repo_root() -> Path:
    configured = os.getenv("KUBEOPS_REPO_ROOT")
    if configured:
        return Path(configured).resolve()
    current = Path.cwd().resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "scenarios" / "families").exists():
            return candidate
    raise typer.BadParameter("could not locate scenarios/families; set KUBEOPS_REPO_ROOT")


def _registry() -> ScenarioFamilyRegistry:
    registry = ScenarioFamilyRegistry()
    registry.load_directory(_repo_root() / "scenarios" / "families")
    return registry


def _lifecycle_registry() -> LifecycleProfileRegistry:
    registry = LifecycleProfileRegistry()
    registry.load_directory(_repo_root() / "lifecycle")
    return registry


def _policy_registry() -> ExecutionPolicyRegistry:
    registry = ExecutionPolicyRegistry()
    registry.load_directory(_repo_root() / "policies")
    return registry


def _operation_runtime(store_dir: Path) -> OperationRuntime:
    return OperationRuntime(build_builtin_action_catalog(), build_default_executor_registry(), FileOperationStore(store_dir))


def _parse_bindings(items: list[str]) -> dict[str, Any]:
    bindings: dict[str, Any] = {}
    for item in items:
        if "=" not in item:
            raise typer.BadParameter(f"binding must have NAME=VALUE form: {item}")
        name, raw = item.split("=", 1)
        try:
            value = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            raise typer.BadParameter(f"invalid value for {name}: {exc}") from exc
        bindings[name] = value
    return bindings




def _load_model(path: Path, model: Any) -> Any:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return model.model_validate(payload)


def _profile_registry() -> OperationalProfileRegistry:
    registry = OperationalProfileRegistry()
    registry.load_directory(_repo_root() / "profiles")
    return registry


@environment_app.command("validate")
def validate_environment(
    environment_path: Path,
    method_id: str | None = typer.Option(None, help="Access method to validate."),
) -> None:
    environment = _load_model(environment_path, EnvironmentDefinition)
    result = EnvironmentIntelligenceService().validate(environment, method_id)
    table = Table(title=f"Access validation: {environment.name}")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Explanation")
    for check in result.checks:
        table.add_row(check.title, str(check.status), check.explanation)
    console.print(table)
    console.print(f"Target fingerprint: [cyan]{result.target_fingerprint}[/cyan]")
    if result.permission_gaps:
        console.print(f"[yellow]{len(result.permission_gaps)} permission gaps detected.[/yellow]")


@environment_app.command("show")
def show_environment(environment_path: Path) -> None:
    environment = _load_model(environment_path, EnvironmentDefinition)
    console.print_json(environment.model_dump_json(indent=2))


@snapshot_app.command("collect")
def collect_snapshot(
    environment_path: Path,
    output: Path = typer.Option(..., help="Write the canonical EnvironmentSnapshot JSON here."),
    method_id: str | None = typer.Option(None, help="Access method to use."),
    resource: list[str] = typer.Option([], "--resource", help="Restrict collection to these kubectl resource names."),
    profile: list[str] = typer.Option([], "--profile", help="Operational profile IDs to evaluate."),
    artifact_dir: Path | None = typer.Option(None, help="Optional artifact output directory."),
) -> None:
    environment = _load_model(environment_path, EnvironmentDefinition)
    registry = _profile_registry()
    profile_ids = profile or environment.operational_profile_ids
    profiles = [registry.get(profile_id) for profile_id in profile_ids]
    result = EnvironmentIntelligenceService().collect(
        environment,
        method_id=method_id,
        resource_types=resource or None,
        profiles=profiles,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result.snapshot.model_dump_json(indent=2), encoding="utf-8")
    if artifact_dir:
        from kubeops_core.artifacts import build_snapshot_artifacts

        store = FileArtifactStore(artifact_dir)
        for artifact in build_snapshot_artifacts(result.bundle, result.snapshot, result.topology, result.assessments):
            store.put(artifact)
    table = Table(title=f"Snapshot {result.snapshot.snapshot_id}")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Status", result.snapshot.status)
    table.add_row("Entities", str(len(result.snapshot.entities)))
    table.add_row("Relationships", str(len(result.snapshot.relationships)))
    table.add_row("Permission gaps", str(len(result.snapshot.permission_gaps)))
    table.add_row("Profiles", str(len(result.assessments)))
    table.add_row("Output", str(output))
    console.print(table)
    for assessment in result.assessments:
        console.print(f"{assessment.profile_id}: [bold]{assessment.status}[/bold]")


@snapshot_app.command("diff")
def compare_snapshots(
    before_path: Path,
    after_path: Path,
    output: Path | None = typer.Option(None, help="Optional JSON output path."),
) -> None:
    before = _load_model(before_path, EnvironmentSnapshot)
    after = _load_model(after_path, EnvironmentSnapshot)
    result = diff_snapshots(before, after)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    table = Table(title="Snapshot diff")
    table.add_column("Change")
    table.add_column("Count")
    for key, value in result.summary.items():
        table.add_row(key.replace("_", " "), str(value))
    console.print(table)
    if output:
        console.print(f"[green]Wrote {output}[/green]")


@snapshot_app.command("show")
def show_snapshot(snapshot_path: Path) -> None:
    snapshot = _load_model(snapshot_path, EnvironmentSnapshot)
    table = Table(title=snapshot.snapshot_id)
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Environment", snapshot.environment_id)
    table.add_row("Status", snapshot.status)
    table.add_row("Captured", snapshot.captured_at_iso)
    table.add_row("Entities", str(len(snapshot.entities)))
    table.add_row("Relationships", str(len(snapshot.relationships)))
    table.add_row("Issues", str(len(snapshot.issues)))
    table.add_row("Permission gaps", str(len(snapshot.permission_gaps)))
    console.print(table)


@profile_app.command("list")
def list_profiles() -> None:
    table = Table(title="Operational profiles")
    table.add_column("Profile")
    table.add_column("Version")
    table.add_column("Templates")
    table.add_column("Title")
    for profile in _profile_registry().values():
        table.add_row(profile.profile_id, profile.version, str(len(profile.invariant_templates)), profile.title)
    console.print(table)


@profile_app.command("show")
def show_profile(profile_id: str) -> None:
    console.print_json(_profile_registry().get(profile_id).model_dump_json(indent=2))


@profile_app.command("evaluate")
def evaluate_profile(
    profile_id: str,
    snapshot_path: Path,
    output: Path | None = typer.Option(None),
) -> None:
    snapshot = _load_model(snapshot_path, EnvironmentSnapshot)
    assessment = HealthAssessmentEngine().assess(_profile_registry().get(profile_id), snapshot)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(assessment.model_dump_json(indent=2), encoding="utf-8")
    table = Table(title=f"{profile_id}: {assessment.status}")
    table.add_column("Invariant")
    table.add_column("Status")
    table.add_column("Explanation")
    for evaluation in assessment.evaluations:
        table.add_row(evaluation.invariant_id, str(evaluation.status), evaluation.explanation)
    console.print(table)

@registry_app.command("list")
def list_registry(category: str | None = typer.Option(None, help="Optional registry category.")) -> None:
    catalog = build_builtin_catalog()
    for family in _registry().values():
        catalog.register(
            RegistryEntry(
                registry_key=family.family_id,
                category="scenario_family",
                version=family.version,
                title=family.title,
                description=family.description,
                capabilities={"inherit"} if family.abstract else {"compile"},
            )
        )
    table = Table(title="KubeOps canonical registry")
    table.add_column("Category")
    table.add_column("Key")
    table.add_column("Version")
    table.add_column("Capabilities")
    for entry in catalog.entries(category):
        table.add_row(entry.category, entry.registry_key, entry.version, ", ".join(sorted(entry.capabilities)) or "—")
    console.print(table)


@family_app.command("list")
def list_families() -> None:
    registry = _registry()
    table = Table(title="KubeOps scenario families")
    table.add_column("Family")
    table.add_column("Version")
    table.add_column("Parent")
    table.add_column("Title")
    for family in registry.values():
        table.add_row(
            family.family_id,
            family.version,
            family.parent_family_id or "—",
            family.title,
        )
    console.print(table)


@family_app.command("show")
def show_family(family_id: str) -> None:
    family = _registry().get(family_id)
    console.print_json(family.model_dump_json(indent=2))


@family_app.command("validate")
def validate_families() -> None:
    registry = _registry()
    for family in registry.values():
        registry.lineage(family.family_id)
    console.print(f"[green]Validated {len(registry)} scenario families.[/green]")


@scenario_app.command("compile")
def compile_scenario(
    family_id: str,
    binding: list[str] = typer.Option([], "--binding", "-b", help="NAME=VALUE binding; may repeat."),
    disturbance: str | None = typer.Option(None, help="Disturbance ID."),
    observation_profile: str | None = typer.Option(None, help="Observation profile ID."),
    output: Path | None = typer.Option(None, help="Write JSON to this path."),
) -> None:
    compiler = ScenarioCompiler(_registry())
    try:
        scenario = compiler.compile(
            family_id,
            _parse_bindings(binding),
            disturbance_id=disturbance,
            observation_profile_id=observation_profile,
        )
    except ScenarioCompileError as exc:
        for error in exc.errors:
            console.print(f"[red]{error}[/red]")
        raise typer.Exit(2)
    payload = scenario.model_dump_json(indent=2)
    if output:
        output.write_text(payload, encoding="utf-8")
        console.print(f"[green]Wrote {output}[/green]")
    else:
        console.print_json(payload)


@scenario_app.command("run")
def run_scenario(
    family_id: str,
    binding: list[str] = typer.Option([], "--binding", "-b"),
    disturbance: str | None = typer.Option(None),
    observation_profile: str | None = typer.Option(None),
    max_time: int = typer.Option(20, min=1),
    artifacts: Path = typer.Option(Path("artifacts"), help="Artifact output directory."),
) -> None:
    compiler = ScenarioCompiler(_registry())
    try:
        scenario = compiler.compile(
            family_id,
            _parse_bindings(binding),
            disturbance_id=disturbance,
            observation_profile_id=observation_profile,
            max_time_seconds=max_time,
        )
    except ScenarioCompileError as exc:
        for error in exc.errors:
            console.print(f"[red]{error}[/red]")
        raise typer.Exit(2)

    run = SimulationEngine().run(scenario)
    store = FileArtifactStore(artifacts)
    for artifact in build_run_artifacts(scenario, run):
        store.put(artifact)

    table = Table(title=f"Simulation {run.run_id}")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Status", str(run.status))
    table.add_row("Family", run.family_id)
    table.add_row("Events", str(len(run.timeline)))
    table.add_row("Snapshots", str(len(run.snapshots)))
    table.add_row("Unhealthy invariants", ", ".join(run.final_summary["unhealthy_invariants"]) or "none")
    table.add_row("Unknown invariants", ", ".join(run.final_summary["unknown_invariants"]) or "none")
    table.add_row("Artifact directory", str(artifacts / run.run_id))
    console.print(table)


@composition_app.command("compile")
def compile_composition(
    spec_path: Path,
    output: Path | None = typer.Option(None, help="Write compiled JSON to this path."),
) -> None:
    payload = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    spec = ScenarioComposition.model_validate(payload)
    scenario = ScenarioComposer(ScenarioCompiler(_registry())).compose(spec)
    rendered = scenario.model_dump_json(indent=2)
    if output:
        output.write_text(rendered, encoding="utf-8")
        console.print(f"[green]Wrote {output}[/green]")
    else:
        console.print_json(rendered)


@composition_app.command("run")
def run_composition(
    spec_path: Path,
    artifacts: Path = typer.Option(Path("artifacts"), help="Artifact output directory."),
) -> None:
    payload = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    spec = ScenarioComposition.model_validate(payload)
    scenario = ScenarioComposer(ScenarioCompiler(_registry())).compose(spec)
    run = SimulationEngine().run(scenario)
    store = FileArtifactStore(artifacts)
    for artifact in build_run_artifacts(scenario, run):
        store.put(artifact)
    console.print(f"[green]{run.status}[/green] {run.run_id}")
    console.print_json(json.dumps(run.final_summary))


@diagnostic_app.command("catalog")
def show_diagnostic_catalog(
    category: str | None = typer.Option(None, help="intent, collector, or template"),
) -> None:
    catalog = build_builtin_diagnostic_catalog()
    rows: list[tuple[str, str, str, str]] = []
    if category in {None, "intent"}:
        rows.extend(("intent", item.intent_id, item.title, item.risk_class) for item in catalog.intents())
    if category in {None, "collector"}:
        rows.extend(("collector", item.collector_id, item.title, item.risk_class) for item in catalog.collectors())
    if category in {None, "template"}:
        rows.extend(("template", item.template_id, item.title, "generic" if item.generic else str(item.specificity)) for item in catalog.templates())
    table = Table(title="KubeOps diagnostic catalog")
    table.add_column("Category")
    table.add_column("Identifier")
    table.add_column("Title")
    table.add_column("Risk / specificity")
    for row in rows:
        table.add_row(*row)
    console.print(table)


@diagnostic_app.command("evaluate")
def evaluate_scenario_diagnosis(
    family_id: str,
    binding: list[str] = typer.Option([], "--binding", "-b"),
    disturbance: str | None = typer.Option(None),
    observation_profile: str | None = typer.Option(None),
    expected_family: list[str] = typer.Option([], "--expected-family"),
    maximum_probe_count: int | None = typer.Option(None, min=0),
    output: Path | None = typer.Option(None, help="Optional diagnostic case JSON output."),
) -> None:
    compiler = ScenarioCompiler(_registry())
    try:
        scenario = compiler.compile(
            family_id,
            _parse_bindings(binding),
            disturbance_id=disturbance,
            observation_profile_id=observation_profile,
        )
    except ScenarioCompileError as exc:
        for error in exc.errors:
            console.print(f"[red]{error}[/red]")
        raise typer.Exit(2)
    run = SimulationEngine().run(scenario)
    expectation = DiagnosticExpectation(
        expected_family_ids=set(expected_family or [family_id.rsplit(".v", 1)[0]]),
        acceptable_parent_family_ids={"operational.invariant_violation"},
        maximum_probe_count=maximum_probe_count,
    )
    result = ScenarioDiagnosisEvaluator().evaluate(scenario, run, expectation)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    table = Table(title=f"Diagnostic evaluation: {scenario.title}")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Passed", str(result.passed))
    table.add_row("Certificate", result.certificate_status)
    table.add_row("Predicted families", ", ".join(result.predicted_family_ids) or "none")
    table.add_row("Expected families", ", ".join(result.expected_family_ids) or "none")
    table.add_row("Recommended probes", str(result.probe_count))
    table.add_row("Precision", str(result.metrics.get("precision", 0.0)))
    table.add_row("Recall", str(result.metrics.get("recall", 0.0)))
    console.print(table)
    for failure in result.failures:
        console.print(f"[yellow]{failure}[/yellow]")
    if output:
        console.print(f"[green]Wrote {output}[/green]")
    if not result.passed:
        raise typer.Exit(1)


@incident_app.command("open")
def open_incident(
    snapshot_path: Path,
    profile_id: str,
    output: Path = typer.Option(..., help="Write the canonical IncidentInvestigation JSON here."),
    artifacts: Path | None = typer.Option(None, help="Optional incident artifact output directory."),
    title: str | None = typer.Option(None),
    initial_symptom: str | None = typer.Option(None),
) -> None:
    snapshot = _load_model(snapshot_path, EnvironmentSnapshot)
    profile = _profile_registry().get(profile_id)
    incident = InvestigationService().open(
        snapshot,
        profile,
        title=title,
        initial_symptom=initial_symptom,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(incident.model_dump_json(indent=2), encoding="utf-8")
    if artifacts:
        store = FileArtifactStore(artifacts)
        for artifact in build_incident_artifacts(incident):
            store.put(artifact)
    table = Table(title=f"Incident {incident.incident_id}")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Status", incident.status)
    table.add_row("Certificate", incident.certificate.status if incident.certificate else "none")
    table.add_row("Symptoms", str(len(incident.symptoms)))
    table.add_row("Evidence facts", str(len(incident.evidence)))
    table.add_row("Hypotheses", str(len(incident.hypotheses)))
    table.add_row("Recommended probes", str(len(incident.probe_plan.probes) if incident.probe_plan else 0))
    table.add_row("Output", str(output))
    console.print(table)


@incident_app.command("show")
def show_incident(incident_path: Path) -> None:
    incident = _load_model(incident_path, IncidentInvestigation)
    table = Table(title=f"{incident.incident_id}: {incident.title}")
    table.add_column("Hypothesis")
    table.add_column("Status")
    table.add_column("Confidence")
    table.add_column("Claim")
    for item in incident.hypotheses:
        table.add_row(item.family_id, item.status, f"{item.confidence:.2f}", item.claim)
    console.print(table)
    if incident.probe_plan and incident.probe_plan.probes:
        probe_table = Table(title="Recommended probes")
        probe_table.add_column("Probe ID")
        probe_table.add_column("Title")
        probe_table.add_column("Information gain")
        probe_table.add_column("Collectors")
        for probe in incident.probe_plan.probes:
            probe_table.add_row(probe.probe_id, probe.title, f"{probe.information_gain_score:.2f}", ", ".join(probe.candidate_collector_ids))
        console.print(probe_table)


@incident_app.command("probe")
def run_incident_probe(
    incident_path: Path,
    snapshot_path: Path,
    profile_id: str,
    probe_id: str,
    output: Path = typer.Option(...),
    artifacts: Path | None = typer.Option(None),
) -> None:
    incident = _load_model(incident_path, IncidentInvestigation)
    snapshot = _load_model(snapshot_path, EnvironmentSnapshot)
    refined = InvestigationService().run_probe(
        incident,
        probe_id,
        snapshot,
        _profile_registry().get(profile_id),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(refined.model_dump_json(indent=2), encoding="utf-8")
    if artifacts:
        store = FileArtifactStore(artifacts)
        for artifact in build_incident_artifacts(refined):
            store.put(artifact)
    console.print(f"[green]Probe completed.[/green] {len(refined.evidence) - len(incident.evidence)} new evidence facts")
    console.print(f"Diagnosis: [bold]{refined.certificate.status if refined.certificate else 'none'}[/bold]")


@lifecycle_app.command("list")
def list_lifecycle_profiles() -> None:
    table = Table(title="Lifecycle profiles")
    table.add_column("Profile")
    table.add_column("Operation")
    table.add_column("Target profile")
    table.add_column("Stages")
    for profile in _lifecycle_registry().values():
        table.add_row(profile.profile_id, profile.operation_type, profile.target_operational_profile_id, str(len(profile.stages)))
    console.print(table)


@lifecycle_app.command("plan")
def plan_lifecycle(
    profile_id: str,
    snapshot_path: Path,
    output: Path = typer.Option(...),
    mode: str = typer.Option("dry_run"),
    policy_id: str | None = typer.Option(None),
) -> None:
    snapshot = _load_model(snapshot_path, EnvironmentSnapshot)
    profile = _lifecycle_registry().get(profile_id)
    plan = LifecyclePlanner(build_builtin_action_catalog()).plan(profile, snapshot, mode=mode, policy_id=policy_id)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    table = Table(title=f"Lifecycle plan: {profile.title}")
    table.add_column("Stage")
    table.add_column("Action")
    table.add_column("Risk")
    table.add_column("Depends on")
    for action in plan.actions:
        table.add_row(action.stage_id or "—", action.title or action.action_type_id, action.risk.risk_class, ", ".join(action.depends_on_action_ids) or "—")
    console.print(table)
    if plan.unsupported_assumptions:
        for item in plan.unsupported_assumptions:
            console.print(f"[yellow]{item}[/yellow]")
    console.print(f"[green]Wrote {output}[/green]")


@policy_app.command("list")
def list_policies() -> None:
    table = Table(title="Execution policies")
    table.add_column("Policy")
    table.add_column("Environment classes")
    table.add_column("Risks")
    table.add_column("Mutation budget")
    for policy in _policy_registry().values():
        table.add_row(policy.policy_id, ", ".join(sorted(policy.environment_classes)), ", ".join(sorted(policy.allowed_risk_classes)), str(policy.mutation_budget))
    console.print(table)


@policy_app.command("actions")
def list_actions() -> None:
    table = Table(title="Typed action catalog")
    table.add_column("Action type")
    table.add_column("Risk")
    table.add_column("Executor")
    table.add_column("Capabilities")
    for action in build_builtin_action_catalog().values():
        table.add_row(action.action_type_id, action.default_risk.risk_class, action.executor_id, ", ".join(sorted(action.required_capabilities)))
    console.print(table)


@operation_app.command("create")
def create_operation(
    plan_path: Path,
    environment_id: str,
    store_dir: Path = typer.Option(Path("operations")),
    mode: str = typer.Option("dry_run"),
    output: Path | None = typer.Option(None),
) -> None:
    plan = _load_model(plan_path, RecoveryPlan)
    runtime = _operation_runtime(store_dir)
    operation = runtime.create(environment_id, plan, mode=mode)
    if output:
        output.write_text(operation.model_dump_json(indent=2), encoding="utf-8")
    console.print(f"[green]{operation.operation_id}[/green] {operation.status} ({operation.mode})")


@operation_app.command("approve")
def approve_operation(
    operation_id: str,
    approver_id: str,
    action_id: str | None = typer.Option(None),
    store_dir: Path = typer.Option(Path("operations")),
    reason: str = typer.Option("Approved from CLI"),
) -> None:
    runtime = _operation_runtime(store_dir)
    operation = runtime.store.load(operation_id)
    approval = ApprovalRecord(
        approval_id=f"approval:{operation_id}:{len(operation.approvals)}", operation_id=operation_id, action_id=action_id,
        approver_id=approver_id, decision="approve", reason=reason, granted_at_iso=utc_now_iso(), policy_id=operation.plan.policy_id,
    )
    operation = runtime.add_approval(operation, approval)
    console.print(f"[green]Approval recorded.[/green] {len(operation.approvals)} total")


@operation_app.command("run")
def run_operation(
    operation_id: str,
    snapshot_path: Path,
    policy_id: str,
    store_dir: Path = typer.Option(Path("operations")),
    adapter_mode: str = typer.Option("simulation", help="simulation or live"),
    capability: list[str] = typer.Option([], "--capability"),
    artifacts: Path | None = typer.Option(None),
) -> None:
    runtime = _operation_runtime(store_dir)
    operation = runtime.store.load(operation_id)
    snapshot = _load_model(snapshot_path, EnvironmentSnapshot)
    world = {item.entity_id: {"observed_state": item.observed_state, "desired_state": item.desired_state, "name": item.name, "namespace": item.namespace} for item in snapshot.entities}
    context = RuntimeContext(
        policy_context=PolicyContext(environment_class="development", capabilities=frozenset(capability), environment_fingerprint=snapshot.source_fingerprint, expected_fingerprint=snapshot.source_fingerprint),
        execution_context=ExecutionContext(operation_id=operation_id, mode=adapter_mode, environment_id=operation.environment_id, simulation_world=world),
        world_provider=lambda: world, relationships_provider=lambda: snapshot.relationships,
    )
    finished = runtime.run(operation, _policy_registry().get(policy_id), context)
    if artifacts:
        artifact_store = FileArtifactStore(artifacts)
        for artifact in build_operation_artifacts(finished): artifact_store.put(artifact)
    console.print(f"[bold]{finished.status}[/bold] certificate={finished.recovery_certificate.status if finished.recovery_certificate else 'none'}")


@operation_app.command("cancel")
def cancel_operation(
    operation_id: str,
    store_dir: Path = typer.Option(Path("operations")),
    reason: str = typer.Option("Cancelled from CLI"),
) -> None:
    runtime = _operation_runtime(store_dir)
    operation = runtime.cancel(runtime.store.load(operation_id), reason)
    console.print(f"[yellow]{operation.operation_id}[/yellow] {operation.status}")


@operation_app.command("show")
def show_operation(operation_id: str, store_dir: Path = typer.Option(Path("operations"))) -> None:
    operation = FileOperationStore(store_dir).load(operation_id)
    table = Table(title=operation.operation_id)
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Status", operation.status)
    table.add_row("Mode", operation.mode)
    table.add_row("Actions", str(len(operation.plan.actions)))
    table.add_row("Receipts", str(len(operation.action_receipts)))
    table.add_row("Approvals", str(len(operation.approvals)))
    table.add_row("Checkpoints", str(len(operation.checkpoints)))
    table.add_row("Certificate", operation.recovery_certificate.status if operation.recovery_certificate else "none")
    console.print(table)


if __name__ == "__main__":
    app()
