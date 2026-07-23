# Release 0.1 scenario basis

The family files under `scenarios/families` are the executable source of truth.
This directory contains representative family and composition fixtures chosen
for semantic coverage rather than as an exhaustive error catalog.

## Family basis

1. `entity.required_absent.v1` — existence and downstream propagation.
2. `dependency.endpoint_unreachable.v1` — layered reachability.
3. `dependency.authentication_failure.v1` — authentication distinct from authorization.
4. `controller.convergence_failure.v1` — bounded progress and delayed effect.

`dependency.failure.v1` is the abstract reusable parent topology from which the
dependency leaf families inherit.

## Composition basis

- `concurrent-network-controller.yaml` — simultaneous independent failures.
- `sequential-absence-authentication.yaml` — time-offset fault sequence.
- `conditional-absence-authentication.yaml` — cross-component predicate activation.
- `masking-hidden-absence.yaml` — one failure hidden by the observation model.
- `recovery-interference.yaml` — a second degradation following a recovery-like stage.

The fixtures compile through the same canonical `ScenarioComposition` model used
by the API, CLI, tests, and UI.
