from __future__ import annotations

from copy import deepcopy
from typing import Any

from kubeops_core.models.observation import Observation, ObservationProfile
from kubeops_core.util import delete_path, set_path


class ObservationProjector:
    def project(
        self,
        history: list[tuple[int, dict[str, dict[str, Any]]]],
        current_time: int,
        profile: ObservationProfile,
    ) -> tuple[dict[str, dict[str, Any]], list[Observation]]:
        latest_truth = history[-1][1]
        observed: dict[str, dict[str, Any]] = {}
        observations: list[Observation] = []
        for entity_id, latest_state in latest_truth.items():
            if entity_id in profile.hidden_entity_ids:
                continue
            lag = profile.lag_seconds.get(entity_id, 0)
            source_time, source_state = self._state_at_or_before(history, current_time - lag)
            if entity_id not in source_state:
                continue
            state = deepcopy(source_state[entity_id])
            for hidden_path in profile.hidden_paths.get(entity_id, set()):
                state = delete_path(state, hidden_path)
            for path, value in profile.contradictory_overrides.get(entity_id, {}).items():
                state = set_path(state, path, value)
            observed[entity_id] = state
            observations.append(
                Observation(
                    observation_id=f"obs-{current_time}-{entity_id}",
                    entity_id=entity_id,
                    observed_at=current_time,
                    state=state,
                    freshness_seconds=max(0, current_time - source_time),
                    profile_id=profile.profile_id,
                    authority="simulated_authoritative" if lag == 0 else "simulated_stale",
                )
            )
        return observed, observations

    @staticmethod
    def _state_at_or_before(
        history: list[tuple[int, dict[str, dict[str, Any]]]],
        target_time: int,
    ) -> tuple[int, dict[str, dict[str, Any]]]:
        selected = history[0]
        for candidate in history:
            if candidate[0] <= target_time:
                selected = candidate
            else:
                break
        return selected
