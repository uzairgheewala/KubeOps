from __future__ import annotations

import hashlib
import json
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict


class SchemaModel(BaseModel):
    """Base class for every canonical KubeOps IR object.

    Models are immutable by default, reject unknown fields, serialize
    deterministically, and expose a content hash suitable for artifact identity.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_assignment=True,
        use_enum_values=True,
    )

    schema_version: str = "kubeops.io/v1"
    kind: ClassVar[str] = "SchemaModel"

    def canonical_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)

    def canonical_json(self) -> str:
        return json.dumps(
            self.canonical_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()
