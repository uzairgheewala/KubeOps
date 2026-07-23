from __future__ import annotations

import json
import os
from pathlib import Path

from kubeops_core.models.operation import OperationRun


class FileOperationStore:
    """Atomic file-backed operation journal used by CLI and single-node control planes."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, operation_id: str) -> Path:
        safe = operation_id.replace("/", "_").replace(":", "_")
        return self.root / safe / "operation.json"

    def save(self, operation: OperationRun) -> Path:
        path = self.path_for(operation.operation_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(operation.model_dump_json(indent=2), encoding="utf-8")
        os.replace(temporary, path)
        return path

    def load(self, operation_id: str) -> OperationRun:
        return OperationRun.model_validate_json(self.path_for(operation_id).read_text(encoding="utf-8"))

    def exists(self, operation_id: str) -> bool:
        return self.path_for(operation_id).exists()
