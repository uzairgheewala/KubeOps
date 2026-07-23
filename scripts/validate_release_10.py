#!/usr/bin/env python3
"""Dependency-light Release 1.0 structural validation.

This complements the executable pytest/Django/Vite/Helm checks. It is designed
for constrained environments and fails on repository-level contract drift.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
for relative in ["packages/kubeops_core", "packages/kubeops_pack_sdk", "packages/kubeops_cli", "control_plane"]:
    sys.path.insert(0, str(ROOT / relative))

EXCLUDED_PARTS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "dist"}


def fail(message: str) -> None:
    raise SystemExit(f"Release 1.0 validation failed: {message}")


def repository_files() -> list[Path]:
    return [
        path for path in ROOT.rglob("*")
        if path.is_file() and not any(part in EXCLUDED_PARTS for part in path.relative_to(ROOT).parts)
    ]


def validate_no_sensitive_files() -> None:
    forbidden_names = {".npmrc", ".pypirc", "id_rsa", "id_ed25519"}
    offenders = [path.relative_to(ROOT).as_posix() for path in repository_files() if path.name in forbidden_names]
    if offenders:
        fail(f"sensitive local configuration is present: {offenders}")


def validate_python() -> int:
    count = 0
    for path in repository_files():
        if path.suffix != ".py":
            continue
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        count += 1
    return count


def validate_json_yaml() -> tuple[int, int]:
    json_count = 0
    yaml_count = 0
    for path in repository_files():
        if path.suffix == ".json":
            json.loads(path.read_text(encoding="utf-8"))
            json_count += 1
        elif path.suffix in {".yaml", ".yml"} and "deploy/helm/kubeops/templates" not in path.as_posix():
            list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
            yaml_count += 1
    return json_count, yaml_count


def nested_value(values: dict[str, Any], dotted: str) -> Any:
    current: Any = values
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            raise KeyError(dotted)
        current = current[part]
    return current


def validate_helm() -> int:
    chart_dir = ROOT / "deploy/helm/kubeops"
    chart = yaml.safe_load((chart_dir / "Chart.yaml").read_text(encoding="utf-8"))
    values = yaml.safe_load((chart_dir / "values.yaml").read_text(encoding="utf-8"))
    if chart["version"] != "1.0.0" or chart["appVersion"] != "1.0.0":
        fail("Helm chart and app versions must both be 1.0.0")
    templates = list((chart_dir / "templates").glob("*"))
    value_ref = re.compile(r"\.Values\.([A-Za-z0-9_.]+)")
    directive = re.compile(r"{{-?\s*(if|range|with|define|end|else)\b[^}]*-?}}")
    for path in templates:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if text.count("{{") != text.count("}}"):
            fail(f"unbalanced Helm delimiters in {path.relative_to(ROOT)}")
        depth = 0
        for match in directive.finditer(text):
            token = match.group(1)
            if token in {"if", "range", "with", "define"}:
                depth += 1
            elif token == "end":
                depth -= 1
                if depth < 0:
                    fail(f"unmatched Helm end in {path.relative_to(ROOT)}")
            elif token == "else" and depth <= 0:
                fail(f"Helm else outside a block in {path.relative_to(ROOT)}")
        if depth != 0:
            fail(f"unclosed Helm block in {path.relative_to(ROOT)}")
        for reference in value_ref.findall(text):
            # Strip template method suffixes that are not part of the value path.
            reference = reference.rstrip(".-")
            try:
                nested_value(values, reference)
            except KeyError:
                fail(f"undefined Helm value .Values.{reference} in {path.relative_to(ROOT)}")
    if values["config"]["artifactBackend"] == "file" and values["api"]["replicas"] != 1:
        fail("default file artifact backend must use exactly one API replica")
    network = (chart_dir / "templates/networkpolicy.yaml").read_text(encoding="utf-8")
    for port in [53, 8000, 8080, 5432, 443, 6443]:
        if f"port: {port}" not in network:
            fail(f"network policy omits required port {port}")
    return len([item for item in templates if item.is_file()])


def call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Attribute):
        return f"{call_name(node.value)}.{node.attr}".strip(".")
    if isinstance(node, ast.Name):
        return node.id
    return ""


def literal_keyword(call: ast.Call, name: str) -> Any:
    for keyword in call.keywords:
        if keyword.arg == name:
            try:
                return ast.literal_eval(keyword.value)
            except Exception:
                return None
    return None


def validate_django_migration_shape() -> tuple[int, int]:
    models_path = ROOT / "control_plane/api/models.py"
    model_tree = ast.parse(models_path.read_text(encoding="utf-8"))
    model_fields: dict[str, set[str]] = {}
    for node in model_tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        if not any(call_name(base).endswith("models.Model") for base in node.bases):
            continue
        fields: set[str] = set()
        for statement in node.body:
            if not isinstance(statement, ast.Assign) or len(statement.targets) != 1 or not isinstance(statement.targets[0], ast.Name):
                continue
            if isinstance(statement.value, ast.Call) and call_name(statement.value.func).startswith("models."):
                fields.add(statement.targets[0].id)
        model_fields[node.name] = fields

    migration_fields: dict[str, set[str]] = {}
    for path in sorted((ROOT / "control_plane/api/migrations").glob("[0-9]*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = call_name(node.func)
            if name.endswith("migrations.CreateModel"):
                model_name = literal_keyword(node, "name")
                fields_node = next((keyword.value for keyword in node.keywords if keyword.arg == "fields"), None)
                parsed_fields: set[str] = set()
                if isinstance(fields_node, (ast.List, ast.Tuple)):
                    for item in fields_node.elts:
                        if (
                            isinstance(item, (ast.Tuple, ast.List))
                            and item.elts
                            and isinstance(item.elts[0], ast.Constant)
                            and isinstance(item.elts[0].value, str)
                        ):
                            parsed_fields.add(item.elts[0].value)
                if isinstance(model_name, str):
                    migration_fields[model_name] = parsed_fields
            elif name.endswith("migrations.AddField"):
                model_name = literal_keyword(node, "model_name")
                field_name = literal_keyword(node, "name")
                if isinstance(model_name, str) and isinstance(field_name, str):
                    canonical = next((key for key in model_fields if key.lower() == model_name.lower()), model_name)
                    migration_fields.setdefault(canonical, set()).add(field_name)
            elif name.endswith("migrations.RemoveField"):
                model_name = literal_keyword(node, "model_name")
                field_name = literal_keyword(node, "name")
                canonical = next((key for key in model_fields if key.lower() == str(model_name).lower()), str(model_name))
                migration_fields.setdefault(canonical, set()).discard(str(field_name))
    missing_models = sorted(set(model_fields) - set(migration_fields))
    if missing_models:
        fail(f"Django models absent from migrations: {missing_models}")
    field_gaps = {
        model: sorted(fields - migration_fields.get(model, set()))
        for model, fields in model_fields.items()
        if fields - migration_fields.get(model, set())
    }
    if field_gaps:
        fail(f"Django model fields absent from migration history: {field_gaps}")
    return len(model_fields), len(migration_fields)


def validate_versions() -> None:
    expected = "1.0.0"
    pyprojects = [
        ROOT / "packages/kubeops_core/pyproject.toml",
        ROOT / "packages/kubeops_pack_sdk/pyproject.toml",
        ROOT / "packages/kubeops_cli/pyproject.toml",
        ROOT / "control_plane/pyproject.toml",
    ]
    for path in pyprojects:
        match = re.search(r'^version\s*=\s*"([^"]+)"', path.read_text(encoding="utf-8"), re.MULTILINE)
        if not match or match.group(1) != expected:
            fail(f"version mismatch in {path.relative_to(ROOT)}")
    package = json.loads((ROOT / "ui/package.json").read_text(encoding="utf-8"))
    if package.get("version") != expected:
        fail("UI package version mismatch")


def validate_registry() -> tuple[int, int]:
    import kubeops_core.models as model_module
    from kubeops_core.models import SchemaModel
    from kubeops_core.registry import build_builtin_catalog

    models = sorted(
        {
            value
            for value in vars(model_module).values()
            if isinstance(value, type) and issubclass(value, SchemaModel) and value is not SchemaModel
        },
        key=lambda item: item.__name__,
    )
    for model in models:
        schema = model.model_json_schema()
        if not isinstance(schema, dict) or not schema.get("title"):
            fail(f"invalid JSON Schema for {model.__name__}")
    snapshot = build_builtin_catalog().snapshot()
    return len(models), len(snapshot.entries)


def main() -> None:
    validate_no_sensitive_files()
    validate_versions()
    python_count = validate_python()
    json_count, yaml_count = validate_json_yaml()
    template_count = validate_helm()
    model_count, migrated_count = validate_django_migration_shape()
    schema_count, registry_count = validate_registry()
    report = {
        "status": "passed",
        "python_files": python_count,
        "json_files": json_count,
        "yaml_files": yaml_count,
        "helm_templates": template_count,
        "django_models": model_count,
        "migration_models": migrated_count,
        "canonical_schemas": schema_count,
        "registry_entries": registry_count,
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
