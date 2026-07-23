from __future__ import annotations

import hashlib
import os
from pathlib import Path
from uuid import uuid4

from kubeops_core.models.security import SecretReference, SecretResolutionReceipt
from kubeops_core.util import utc_now_iso


class SecretResolver:
    def __init__(self, memory: dict[str, str] | None = None) -> None:
        self.memory = memory or {}

    def resolve(self, reference: SecretReference, consumer_id: str) -> tuple[str, SecretResolutionReceipt]:
        if reference.allowed_consumers and consumer_id not in reference.allowed_consumers:
            raise PermissionError(f"consumer {consumer_id!r} is not allowed to resolve {reference.secret_ref_id}")
        if reference.provider == "environment":
            value = os.environ.get(reference.locator)
            if value is None:
                raise KeyError(f"environment variable {reference.locator!r} is not set")
        elif reference.provider == "file":
            path = Path(reference.locator)
            value = path.read_text(encoding="utf-8").rstrip("\n")
        elif reference.provider == "memory":
            value = self.memory[reference.locator]
        else:
            raise NotImplementedError("external secret providers require a configured integration adapter")
        receipt = SecretResolutionReceipt(
            receipt_id=f"secret-receipt:{uuid4()}", secret_ref_id=reference.secret_ref_id, consumer_id=consumer_id,
            provider=reference.provider, resolved_at_iso=utc_now_iso(), expires_at_iso=reference.expires_at_iso,
            material_hash=hashlib.sha256(value.encode()).hexdigest(), redacted_locator=self._redact(reference.locator),
        )
        return value, receipt

    @staticmethod
    def _redact(locator: str) -> str:
        if len(locator) <= 4:
            return "****"
        return f"{locator[:2]}***{locator[-2:]}"
