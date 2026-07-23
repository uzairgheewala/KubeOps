from __future__ import annotations

from collections import Counter
from pathlib import Path
from uuid import uuid4

import yaml

from kubeops_core.models.pack import (
    KnowledgePackManifest,
    PackResolution,
    PackStatus,
    PackValidationIssue,
)
from kubeops_core.models.security import PackSignature, PackTrustPolicy, PackVerificationResult
from kubeops_core.supply_chain.signing import PackSigner
from kubeops_core.util import utc_now_iso

from .runtime import PackRuntime
from .versioning import satisfies


class PackManager:
    def __init__(self, *, kubeops_version: str = "1.0.0", kubernetes_version: str | None = None) -> None:
        self.kubeops_version = kubeops_version
        self.kubernetes_version = kubernetes_version
        self._manifests: dict[str, KnowledgePackManifest] = {}
        self._sources: dict[str, str] = {}

    def register(self, manifest: KnowledgePackManifest, *, source: str = "memory", replace: bool = False) -> None:
        existing = self._manifests.get(manifest.pack_id)
        if existing and not replace:
            if existing.content_hash != manifest.content_hash:
                raise ValueError(f"pack {manifest.pack_id!r} already registered with different content")
            return
        self._manifests[manifest.pack_id] = manifest
        self._sources[manifest.pack_id] = source

    def load_directory(self, directory: str | Path) -> int:
        count = 0
        for path in sorted(Path(directory).glob("*/pack.y*ml")):
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
            if payload:
                self.register(KnowledgePackManifest.model_validate(payload), source=str(path))
                count += 1
        return count

    def values(self) -> list[KnowledgePackManifest]:
        return [self._manifests[key] for key in sorted(self._manifests)]

    def get(self, pack_id: str) -> KnowledgePackManifest:
        try:
            return self._manifests[pack_id]
        except KeyError as exc:
            raise KeyError(f"unknown knowledge pack {pack_id!r}") from exc

    def source(self, pack_id: str) -> str:
        return self._sources[pack_id]

    def validate(self, pack_id: str, *, active_pack_ids: set[str] | None = None) -> list[PackValidationIssue]:
        manifest = self.get(pack_id)
        issues: list[PackValidationIssue] = []
        if not satisfies(self.kubeops_version, manifest.compatibility.kubeops_constraint):
            issues.append(PackValidationIssue(code="kubeops_version_incompatible", severity="error", message=f"KubeOps {self.kubeops_version} does not satisfy {manifest.compatibility.kubeops_constraint}", pack_id=pack_id))
        if self.kubernetes_version and manifest.compatibility.kubernetes_constraint and not satisfies(self.kubernetes_version, manifest.compatibility.kubernetes_constraint):
            issues.append(PackValidationIssue(code="kubernetes_version_incompatible", severity="error", message=f"Kubernetes {self.kubernetes_version} does not satisfy {manifest.compatibility.kubernetes_constraint}", pack_id=pack_id))
        for dependency in manifest.dependencies:
            if dependency.pack_id not in self._manifests and not dependency.optional:
                issues.append(PackValidationIssue(code="missing_dependency", severity="error", message=f"required pack {dependency.pack_id} is not installed", pack_id=pack_id))
            elif dependency.pack_id in self._manifests and not satisfies(self._manifests[dependency.pack_id].version, dependency.version_constraint):
                issues.append(PackValidationIssue(code="dependency_version_incompatible", severity="error", message=f"{dependency.pack_id} {self._manifests[dependency.pack_id].version} does not satisfy {dependency.version_constraint}", pack_id=pack_id))
        conflict_scope = set(self._manifests) if active_pack_ids is None else active_pack_ids
        for conflict in manifest.conflicts_with:
            if conflict in conflict_scope:
                issues.append(PackValidationIssue(code="pack_conflict", severity="error", message=f"conflicts with selected pack {conflict}", pack_id=pack_id, details={"conflicting_pack_id": conflict}))
        issues.extend(self._duplicate_contribution_issues(manifest))
        return issues

    @staticmethod
    def _duplicate_contribution_issues(manifest: KnowledgePackManifest) -> list[PackValidationIssue]:
        identifiers: list[tuple[str, str]] = []
        fields = manifest.contributions
        mappings = {
            "entity_classifier": [(item.classifier_id, item) for item in fields.entity_classifiers],
            "relationship_resolver": [(item.resolver_id, item) for item in fields.relationship_resolvers],
            "operational_profile": [(item.profile_id, item) for item in fields.operational_profiles],
            "evidence_intent": [(item.intent_id, item) for item in fields.evidence_intents],
            "collector": [(item.collector_id, item) for item in fields.collectors],
            "causal_template": [(item.template_id, item) for item in fields.causal_templates],
            "action_type": [(item.action_type_id, item) for item in fields.action_types],
            "lifecycle_profile": [(item.profile_id, item) for item in fields.lifecycle_profiles],
            "verification_template": [(item.condition_id, item) for item in fields.verification_templates],
            "redaction_rule": [(item.rule_id, item) for item in fields.redaction_rules],
        }
        for category, values in mappings.items():
            identifiers.extend((category, key) for key, _ in values)
        counts = Counter(identifiers)
        return [
            PackValidationIssue(code="duplicate_contribution", severity="error", message=f"duplicate {category} contribution {key}", pack_id=manifest.pack_id, contribution_id=key)
            for (category, key), count in counts.items() if count > 1
        ]

    @staticmethod
    def _contribution_identifiers(manifest: KnowledgePackManifest) -> list[tuple[str, str]]:
        fields = manifest.contributions
        return [
            *[("entity_classifier", item.classifier_id) for item in fields.entity_classifiers],
            *[("relationship_resolver", item.resolver_id) for item in fields.relationship_resolvers],
            *[("operational_profile", item.profile_id) for item in fields.operational_profiles],
            *[("evidence_intent", item.intent_id) for item in fields.evidence_intents],
            *[("collector", item.collector_id) for item in fields.collectors],
            *[("causal_template", item.template_id) for item in fields.causal_templates],
            *[("action_type", item.action_type_id) for item in fields.action_types],
            *[("lifecycle_profile", item.profile_id) for item in fields.lifecycle_profiles],
            *[("verification_template", item.condition_id) for item in fields.verification_templates],
            *[("redaction_rule", item.rule_id) for item in fields.redaction_rules],
        ]

    def _cross_pack_contribution_issues(self, pack_ids: set[str]) -> list[PackValidationIssue]:
        owners: dict[tuple[str, str], list[str]] = {}
        for pack_id in sorted(pack_ids):
            for identity in self._contribution_identifiers(self.get(pack_id)):
                owners.setdefault(identity, []).append(pack_id)
        issues: list[PackValidationIssue] = []
        for (category, contribution_id), pack_owners in sorted(owners.items()):
            if len(pack_owners) < 2:
                continue
            for pack_id in pack_owners:
                issues.append(
                    PackValidationIssue(
                        code="cross_pack_contribution_collision",
                        severity="error",
                        message=f"{category} contribution {contribution_id!r} is also provided by {sorted(set(pack_owners) - {pack_id})}",
                        pack_id=pack_id,
                        contribution_id=contribution_id,
                        details={"category": category, "owners": pack_owners},
                    )
                )
        return issues

    def resolve(
        self,
        requested_pack_ids: list[str] | None = None,
        *,
        trust_policy: PackTrustPolicy | None = None,
        signatures: dict[str, PackSignature] | None = None,
        trusted_secrets: dict[str, str] | None = None,
        trusted_public_keys: dict[str, str] | None = None,
    ) -> PackResolution:
        requested = list(requested_pack_ids or sorted(self._manifests))
        unknown = sorted(set(requested) - set(self._manifests))
        if unknown:
            raise KeyError(f"unknown requested packs: {unknown}")
        closure: set[str] = set()

        def include(pack_id: str) -> None:
            if pack_id in closure:
                return
            closure.add(pack_id)
            for dependency in self.get(pack_id).dependencies:
                if dependency.pack_id in self._manifests:
                    include(dependency.pack_id)

        for pack_id in requested:
            include(pack_id)

        dependencies = {
            pack_id: {item.pack_id for item in self.get(pack_id).dependencies if item.pack_id in closure}
            for pack_id in closure
        }
        ordered: list[str] = []
        remaining = {key: set(value) for key, value in dependencies.items()}
        while remaining:
            ready = sorted((key for key, value in remaining.items() if not value), key=lambda key: (self.get(key).priority, key))
            if not ready:
                cycle = sorted(remaining)
                issue = PackValidationIssue(code="dependency_cycle", severity="error", message=f"pack dependency cycle: {cycle}")
                return self._resolution(requested, ordered, [], cycle, [issue], {})
            for pack_id in ready:
                ordered.append(pack_id)
                remaining.pop(pack_id)
                for values in remaining.values():
                    values.discard(pack_id)

        issues: list[PackValidationIssue] = []
        trust_results: dict[str, PackVerificationResult] = {}
        if trust_policy is not None:
            signatures = signatures or {}
            trusted_secrets = trusted_secrets or {}
            trusted_public_keys = trusted_public_keys or {}
            for pack_id in closure:
                result = PackSigner.verify(
                    self.get(pack_id), signatures.get(pack_id), trust_policy,
                    trusted_secrets=trusted_secrets, trusted_public_keys=trusted_public_keys,
                )
                trust_results[pack_id] = result
                if result.outcome != "trusted":
                    issues.append(PackValidationIssue(
                        code="pack_untrusted", severity="error",
                        message=f"pack trust verification returned {result.outcome}: {result.reasons}",
                        pack_id=pack_id, details=result.model_dump(mode="json"),
                    ))
        cross_pack_issues = self._cross_pack_contribution_issues(closure)
        preexisting_issues = list(issues)
        issues = []
        active: list[str] = []
        blocked: list[str] = []
        for pack_id in ordered:
            current = [*self.validate(pack_id, active_pack_ids=closure), *[item for item in preexisting_issues if item.pack_id == pack_id], *[item for item in cross_pack_issues if item.pack_id == pack_id]]
            dependency_blocked = any(item.pack_id in blocked and not item.optional for item in self.get(pack_id).dependencies)
            if dependency_blocked:
                current.append(PackValidationIssue(code="dependency_blocked", severity="error", message="one or more required dependencies are blocked", pack_id=pack_id))
            issues.extend(current)
            if any(item.severity == "error" for item in current):
                blocked.append(pack_id)
            else:
                active.append(pack_id)
        return self._resolution(requested, ordered, active, blocked, issues, trust_results)

    def _resolution(self, requested: list[str], ordered: list[str], active: list[str], blocked: list[str], issues: list[PackValidationIssue], trust_results: dict[str, PackVerificationResult] | None = None) -> PackResolution:
        trust_results = trust_results or {}
        statuses: list[PackStatus] = []
        for pack_id in ordered:
            manifest = self.get(pack_id)
            pack_issues = [item for item in issues if item.pack_id in {None, pack_id}]
            state = "active" if pack_id in active else "blocked"
            statuses.append(PackStatus(pack_id=pack_id, version=manifest.version, state=state, source=self.source(pack_id), enabled=True, resolved_dependencies=[item.pack_id for item in manifest.dependencies if item.pack_id in ordered], contribution_counts=manifest.contributions.counts(), issues=pack_issues, manifest_hash=manifest.content_hash, trust_outcome=(trust_results.get(pack_id).outcome if pack_id in trust_results else None), signature_id=(trust_results.get(pack_id).signature_id if pack_id in trust_results else None)))
        counter: Counter[str] = Counter()
        for pack_id in active:
            counter.update(self.get(pack_id).contributions.counts())
        return PackResolution(resolution_id=f"pack-resolution:{uuid4()}", created_at_iso=utc_now_iso(), requested_pack_ids=requested, ordered_pack_ids=ordered, active_pack_ids=active, blocked_pack_ids=blocked, statuses=statuses, issues=issues, contribution_counts=dict(sorted(counter.items())))

    def runtime(
        self,
        requested_pack_ids: list[str] | None = None,
        *,
        trust_policy: PackTrustPolicy | None = None,
        signatures: dict[str, PackSignature] | None = None,
        trusted_secrets: dict[str, str] | None = None,
        trusted_public_keys: dict[str, str] | None = None,
    ) -> PackRuntime:
        resolution = self.resolve(
            requested_pack_ids, trust_policy=trust_policy, signatures=signatures,
            trusted_secrets=trusted_secrets, trusted_public_keys=trusted_public_keys,
        )
        manifests = tuple(self.get(pack_id) for pack_id in resolution.active_pack_ids)
        return PackRuntime(resolution=resolution, manifests=manifests)
