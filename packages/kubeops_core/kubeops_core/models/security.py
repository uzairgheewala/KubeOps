from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import Field

from .base import SchemaModel


class SecretReference(SchemaModel):
    kind: ClassVar[str] = "SecretReference"

    secret_ref_id: str
    organization_id: str
    workspace_id: str
    provider: Literal["environment", "file", "memory", "external"]
    locator: str
    version: str | None = None
    purpose: str = ""
    allowed_consumers: set[str] = Field(default_factory=set)
    expires_at_iso: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SecretResolutionReceipt(SchemaModel):
    kind: ClassVar[str] = "SecretResolutionReceipt"

    receipt_id: str
    secret_ref_id: str
    consumer_id: str
    provider: str
    resolved_at_iso: str
    expires_at_iso: str | None = None
    material_hash: str
    redacted_locator: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class PackSignature(SchemaModel):
    kind: ClassVar[str] = "PackSignature"

    signature_id: str
    pack_id: str
    pack_version: str
    manifest_hash: str
    scheme: Literal["hmac-sha256", "ed25519"] = "hmac-sha256"
    key_id: str
    signature: str
    signed_at_iso: str
    signer: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class PackTrustPolicy(SchemaModel):
    kind: ClassVar[str] = "PackTrustPolicy"

    policy_id: str
    organization_id: str
    workspace_id: str
    require_signature: bool = True
    allowed_schemes: set[str] = Field(default_factory=lambda: {"hmac-sha256", "ed25519"})
    require_asymmetric: bool = False
    trusted_key_ids: set[str] = Field(default_factory=set)
    trusted_signers: set[str] = Field(default_factory=set)
    allow_unsigned_pack_ids: set[str] = Field(default_factory=set)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PackVerificationResult(SchemaModel):
    kind: ClassVar[str] = "PackVerificationResult"

    verification_id: str
    pack_id: str
    pack_version: str
    manifest_hash: str
    outcome: Literal["trusted", "untrusted", "unsigned", "invalid"]
    signature_id: str | None = None
    key_id: str | None = None
    reasons: list[str] = Field(default_factory=list)
    verified_at_iso: str
    metadata: dict[str, Any] = Field(default_factory=dict)
