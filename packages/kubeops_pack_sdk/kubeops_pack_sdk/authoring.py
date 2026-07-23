from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from kubeops_core.models.pack import KnowledgePackManifest, PackValidationIssue
from kubeops_core.packs import PackManager


def load_manifest(path: str | Path) -> KnowledgePackManifest:
    payload: Any = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return KnowledgePackManifest.model_validate(payload)


def validate_manifest(path: str | Path, *, packs_root: str | Path | None = None) -> list[PackValidationIssue]:
    manifest = load_manifest(path)
    manager = PackManager()
    if packs_root:
        manager.load_directory(packs_root)
    manager.register(manifest, source=str(path), replace=True)
    return manager.validate(manifest.pack_id)


def scaffold_pack(root: str | Path, *, pack_id: str, title: str, pack_kind: str) -> Path:
    target = Path(root) / pack_id
    target.mkdir(parents=True, exist_ok=False)
    manifest = KnowledgePackManifest(pack_id=pack_id, version="0.1.0", title=title, pack_kind=pack_kind)  # type: ignore[arg-type]
    path = target / "pack.yaml"
    path.write_text(yaml.safe_dump(manifest.model_dump(mode="json", exclude_none=True), sort_keys=False), encoding="utf-8")
    return path
