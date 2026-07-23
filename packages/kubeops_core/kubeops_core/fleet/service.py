from __future__ import annotations

from collections import Counter, defaultdict, deque
from uuid import uuid4

from kubeops_core.models.fleet import (
    CommonCauseFinding,
    FleetAssessment,
    FleetDefinition,
    FleetEnvironmentStatus,
    FleetOperationPlan,
    FleetOperationWave,
)
from kubeops_core.util import utc_now_iso

_STATUS_ORDER = {"healthy": 0, "quiesced": 0, "recovering": 1, "degraded": 2, "unknown": 3, "unavailable": 4}


class FleetService:
    def assess(
        self,
        fleet: FleetDefinition,
        statuses: list[FleetEnvironmentStatus],
        *,
        incident_families: dict[str, list[str]] | None = None,
        shared_factors: dict[str, dict[str, str]] | None = None,
    ) -> FleetAssessment:
        by_environment = {item.environment_id: item for item in statuses}
        missing = [member.environment_id for member in fleet.members if member.environment_id not in by_environment]
        environment_statuses = list(statuses)
        for environment_id in missing:
            environment_statuses.append(FleetEnvironmentStatus(environment_id=environment_id, status="unknown", reasons=["no current fleet observation"] ))
        dependency_violations: list[str] = []
        for dependency in fleet.dependencies:
            target = by_environment.get(dependency.target_environment_id)
            if target is None or target.status not in {"healthy", "recovering", "quiesced"}:
                dependency_violations.append(
                    f"{dependency.source_environment_id} depends on unhealthy {dependency.target_environment_id} via {dependency.relationship_type}"
                )
        common_causes = self._common_causes(environment_statuses, incident_families or {}, shared_factors or {})
        worst = max((_STATUS_ORDER.get(item.status, 3) for item in environment_statuses), default=3)
        status = next(key for key, value in _STATUS_ORDER.items() if value == worst)
        if dependency_violations and status == "healthy":
            status = "degraded"
        counts = Counter(item.status for item in environment_statuses)
        return FleetAssessment(
            assessment_id=f"fleet-assessment:{uuid4()}",
            fleet_id=fleet.fleet_id,
            status=status,  # type: ignore[arg-type]
            generated_at_iso=utc_now_iso(),
            environments=sorted(environment_statuses, key=lambda item: item.environment_id),
            common_causes=common_causes,
            dependency_violations=dependency_violations,
            summary=dict(sorted(counts.items())),
        )

    def _common_causes(
        self,
        statuses: list[FleetEnvironmentStatus],
        incident_families: dict[str, list[str]],
        shared_factors: dict[str, dict[str, str]],
    ) -> list[CommonCauseFinding]:
        by_family: dict[str, list[str]] = defaultdict(list)
        for status in statuses:
            for family in incident_families.get(status.environment_id, []):
                by_family[family].append(status.environment_id)
        findings: list[CommonCauseFinding] = []
        for family, environment_ids in sorted(by_family.items()):
            unique = sorted(set(environment_ids))
            if len(unique) < 2:
                continue
            factor_counts: Counter[tuple[str, str]] = Counter()
            for environment_id in unique:
                factor_counts.update(shared_factors.get(environment_id, {}).items())
            shared = {key: value for (key, value), count in factor_counts.items() if count == len(unique)}
            findings.append(
                CommonCauseFinding(
                    finding_id=f"common-cause:{uuid4()}",
                    family_id=family,
                    title=f"{family} affects {len(unique)} environments",
                    environment_ids=unique,
                    confidence=min(0.99, 0.6 + 0.1 * len(unique) + 0.05 * len(shared)),
                    shared_factors=shared,
                    evidence=[f"family {family} observed in {environment_id}" for environment_id in unique],
                )
            )
        return findings

    def plan_operation(self, fleet: FleetDefinition, operation_type: str) -> FleetOperationPlan:
        members = {item.environment_id for item in fleet.members}
        outgoing: dict[str, set[str]] = {item: set() for item in members}
        indegree: dict[str, int] = {item: 0 for item in members}
        for dependency in fleet.dependencies:
            if operation_type == "shutdown":
                source, target = dependency.source_environment_id, dependency.target_environment_id
            else:
                source, target = dependency.target_environment_id, dependency.source_environment_id
            if target not in outgoing[source]:
                outgoing[source].add(target)
                indegree[target] += 1
        ready = deque(sorted(item for item, degree in indegree.items() if degree == 0))
        waves: list[FleetOperationWave] = []
        processed: set[str] = set()
        while ready:
            batch: list[str] = []
            while ready and len(batch) < fleet.max_parallel_operations:
                item = ready.popleft()
                batch.append(item)
                processed.add(item)
            waves.append(FleetOperationWave(wave_index=len(waves), environment_ids=batch))
            for item in batch:
                for target in sorted(outgoing[item]):
                    indegree[target] -= 1
                    if indegree[target] == 0:
                        ready.append(target)
        warnings: list[str] = []
        if processed != members:
            cycle_members = sorted(members - processed)
            warnings.append(f"dependency cycle prevents complete wave plan: {cycle_members}")
            waves.append(FleetOperationWave(wave_index=len(waves), environment_ids=cycle_members, rationale=["manual ordering required due to dependency cycle"]))
        return FleetOperationPlan(
            plan_id=f"fleet-plan:{uuid4()}",
            fleet_id=fleet.fleet_id,
            operation_type=operation_type,  # type: ignore[arg-type]
            created_at_iso=utc_now_iso(),
            waves=waves,
            max_parallel_operations=fleet.max_parallel_operations,
            warnings=warnings,
        )
