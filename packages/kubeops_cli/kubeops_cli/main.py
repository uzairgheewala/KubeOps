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
from kubeops_core.models.registry import RegistryEntry
from kubeops_core.registry import ScenarioFamilyRegistry, build_builtin_catalog
from kubeops_core.scenarios import ScenarioCompileError, ScenarioCompiler, ScenarioComposer
from kubeops_core.simulator import SimulationEngine

app = typer.Typer(no_args_is_help=True, help="KubeOps Release 0.1 scenario and simulation CLI.")
family_app = typer.Typer(no_args_is_help=True, help="Inspect scenario families.")
scenario_app = typer.Typer(no_args_is_help=True, help="Compile and execute scenarios.")
composition_app = typer.Typer(no_args_is_help=True, help="Compile and execute scenario compositions.")
registry_app = typer.Typer(no_args_is_help=True, help="Inspect canonical extension registries.")
app.add_typer(family_app, name="family")
app.add_typer(scenario_app, name="scenario")
app.add_typer(composition_app, name="composition")
app.add_typer(registry_app, name="registry")
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
