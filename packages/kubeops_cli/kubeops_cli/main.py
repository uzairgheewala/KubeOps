from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import typer
import yaml
from rich.console import Console
from rich.table import Table

from kubeops_core.artifacts import FileArtifactStore, build_run_artifacts
from kubeops_core.models.composition import ScenarioComposition
from kubeops_core.discovery import diff_snapshots
from kubeops_core.environments import EnvironmentIntelligenceService
from kubeops_core.health import HealthAssessmentEngine
from kubeops_core.models import EnvironmentDefinition, EnvironmentSnapshot
from kubeops_core.profiles import OperationalProfileRegistry
from kubeops_core.models.registry import RegistryEntry
from kubeops_core.registry import ScenarioFamilyRegistry, build_builtin_catalog
from kubeops_core.scenarios import ScenarioCompileError, ScenarioCompiler, ScenarioComposer
from kubeops_core.simulator import SimulationEngine

app = typer.Typer(no_args_is_help=True, help="KubeOps Release 0.2 read-only intelligence and scenario CLI.")
family_app = typer.Typer(no_args_is_help=True, help="Inspect scenario families.")
scenario_app = typer.Typer(no_args_is_help=True, help="Compile and execute scenarios.")
composition_app = typer.Typer(no_args_is_help=True, help="Compile and execute scenario compositions.")
registry_app = typer.Typer(no_args_is_help=True, help="Inspect canonical extension registries.")
environment_app = typer.Typer(no_args_is_help=True, help="Validate environment access definitions.")
snapshot_app = typer.Typer(no_args_is_help=True, help="Collect, inspect, and compare read-only snapshots.")
profile_app = typer.Typer(no_args_is_help=True, help="Inspect and evaluate operational profiles.")
app.add_typer(family_app, name="family")
app.add_typer(scenario_app, name="scenario")
app.add_typer(composition_app, name="composition")
app.add_typer(registry_app, name="registry")
app.add_typer(environment_app, name="environment")
app.add_typer(snapshot_app, name="snapshot")
app.add_typer(profile_app, name="profile")
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


if __name__ == "__main__":
    app()
