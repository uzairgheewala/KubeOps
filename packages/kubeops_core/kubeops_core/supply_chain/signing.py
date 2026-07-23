from __future__ import annotations

import base64
import hashlib
import hmac
from uuid import uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key

from kubeops_core.models.pack import KnowledgePackManifest
from kubeops_core.models.security import PackSignature, PackTrustPolicy, PackVerificationResult
from kubeops_core.util import utc_now_iso


class PackSigner:
    @staticmethod
    def sign(
        manifest: KnowledgePackManifest,
        *,
        key_id: str,
        secret: str,
        signer: str,
        scheme: str = "hmac-sha256",
    ) -> PackSignature:
        payload = manifest.content_hash.encode()
        if scheme == "hmac-sha256":
            signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        elif scheme == "ed25519":
            key = load_pem_private_key(secret.encode(), password=None)
            if not isinstance(key, Ed25519PrivateKey):
                raise ValueError("Ed25519 signing requires an Ed25519 PEM private key")
            signature = base64.b64encode(key.sign(payload)).decode()
        else:
            raise ValueError(f"unsupported pack signature scheme {scheme!r}")
        return PackSignature(
            signature_id=f"pack-signature:{uuid4()}",
            pack_id=manifest.pack_id,
            pack_version=manifest.version,
            manifest_hash=manifest.content_hash,
            scheme=scheme,
            key_id=key_id,
            signature=signature,
            signed_at_iso=utc_now_iso(),
            signer=signer,
        )

    @staticmethod
    def verify(
        manifest: KnowledgePackManifest,
        signature: PackSignature | None,
        policy: PackTrustPolicy,
        *,
        trusted_secrets: dict[str, str] | None = None,
        trusted_public_keys: dict[str, str] | None = None,
    ) -> PackVerificationResult:
        trusted_secrets = trusted_secrets or {}
        trusted_public_keys = trusted_public_keys or {}
        reasons: list[str] = []
        if signature is None:
            outcome = (
                "trusted"
                if manifest.pack_id in policy.allow_unsigned_pack_ids or not policy.require_signature
                else "unsigned"
            )
            if outcome == "unsigned":
                reasons.append("pack signature is required by policy")
            return PackVerificationResult(
                verification_id=f"pack-verification:{uuid4()}",
                pack_id=manifest.pack_id,
                pack_version=manifest.version,
                manifest_hash=manifest.content_hash,
                outcome=outcome,
                reasons=reasons,
                verified_at_iso=utc_now_iso(),
            )

        if signature.scheme not in policy.allowed_schemes:
            reasons.append(f"signature scheme {signature.scheme} is not allowed")
        if policy.require_asymmetric and signature.scheme != "ed25519":
            reasons.append("policy requires an asymmetric signature scheme")
        if policy.trusted_key_ids and signature.key_id not in policy.trusted_key_ids:
            reasons.append(f"key {signature.key_id} is not trusted")
        if policy.trusted_signers and signature.signer not in policy.trusted_signers:
            reasons.append(f"signer {signature.signer} is not trusted")
        if signature.manifest_hash != manifest.content_hash:
            reasons.append("signature manifest hash does not match current manifest")

        if not reasons:
            if signature.scheme == "hmac-sha256":
                secret = trusted_secrets.get(signature.key_id)
                if secret is None:
                    reasons.append("trusted HMAC verification material is unavailable")
                elif not hmac.compare_digest(
                    signature.signature,
                    hmac.new(secret.encode(), manifest.content_hash.encode(), hashlib.sha256).hexdigest(),
                ):
                    reasons.append("signature is invalid")
            elif signature.scheme == "ed25519":
                public_material = trusted_public_keys.get(signature.key_id)
                if public_material is None:
                    reasons.append("trusted Ed25519 public key is unavailable")
                else:
                    try:
                        key = load_pem_public_key(public_material.encode())
                        if not isinstance(key, Ed25519PublicKey):
                            raise ValueError("verification key is not Ed25519")
                        key.verify(base64.b64decode(signature.signature, validate=True), manifest.content_hash.encode())
                    except (InvalidSignature, ValueError, TypeError) as exc:
                        reasons.append(f"signature is invalid: {type(exc).__name__}")
            else:
                reasons.append(f"unsupported signature scheme {signature.scheme}")

        outcome = "trusted" if not reasons else "invalid"
        return PackVerificationResult(
            verification_id=f"pack-verification:{uuid4()}",
            pack_id=manifest.pack_id,
            pack_version=manifest.version,
            manifest_hash=manifest.content_hash,
            outcome=outcome,
            signature_id=signature.signature_id,
            key_id=signature.key_id,
            reasons=reasons,
            verified_at_iso=utc_now_iso(),
            metadata={"scheme": signature.scheme},
        )
