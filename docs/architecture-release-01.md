# Release 0.1 detailed architecture

## Authority boundary

Release 0.1 has zero live-cluster authority. All transitions occur inside a
`MutableWorld`. This lets the scenario grammar, invariant semantics, history
contracts, and future safety-sensitive IR stabilize before collectors or
executors are introduced.

The release nevertheless defines forward-compatible schemas for evidence
intents, symptoms, hypotheses, probes, action definitions and instances,
execution policies, recovery plans, verification conditions and results, and
diagnosis/recovery certificates. Those objects are inspectable and testable but
are not granted live authority in Release 0.1.

## Effective scenario family

A client never needs to manually combine parent and child family definitions.
`ScenarioCompiler.effective_family()` resolves the inheritance lattice and
returns the effective parameter, topology, invariant, transition-rule,
observation-profile, and disturbance contract.

Named blueprint elements merge by semantic identity. A child family can refine
only the provider state, invariant, transition rule, or observation profile it
specializes while retaining the parent topology.

## Scenario composition

`ScenarioComposer` compiles multiple family instances into one namespaced
world. Release 0.1 implements:

- Concurrent composition.
- Sequential composition.
- Conditional activation.
- Observation masking.
- Recovery-interference structure.

Component aliases become stable namespace prefixes, bridge relationships can
connect component worlds, and all entity references inside predicates,
mutations, rules, and profiles are rewritten structurally.

## Deterministic simulation

The simulator uses an ordered priority queue keyed by simulation time and stable
insertion order. No wall-clock time influences world evolution. Run timestamps
identify artifact creation, but are not inputs to state transitions.

One-shot transition-rule firing is tracked by structural rule identity, not by
parsing event names. This preserves correctness after composition namespaces
rules and mutations.

## Temporal invariants

The invariant engine supports:

- Immediate predicates.
- Bounded eventuality through `eventually` and `within_seconds`.
- Stability windows through `stable_for` and `stable_for_seconds`.

Evaluations can be `healthy`, `unhealthy`, `pending`, or `unknown`. Unknown is a
first-class result when required evidence is absent or hidden.

## Observation separation

`truth_state` and `observed_state` coexist in every snapshot. Invariants are
evaluated against observed state. Observation profiles support:

- Hidden entities.
- Hidden state paths.
- Per-entity lag.
- Contradictory overrides.

This allows one underlying disturbance to be replayed under full, partial,
delayed, stale-like, or contradictory visibility without changing world truth.

## Artifact chain

Every persisted run produces immutable artifacts for:

- Compiled scenario instance.
- Event timeline.
- Snapshot sequence.
- Observation set.
- Run manifest.

Payloads are canonically JSON-encoded and SHA-256 hashed. The manifest records
explicit derivation links to the source artifacts. Django stores searchable
metadata while the file artifact-store adapter stores payloads atomically.

## Runtime surfaces

The same canonical models are exposed through:

- Python SDK imports.
- Typer/Rich CLI.
- Django REST API.
- React Scenario Lab.
- React Composition Lab.
- Canonical registry and JSON Schema inspector.
- Run artifact explorer.

## Known Release 0.1 limitations

- No live Kubernetes discovery or mutation.
- No fixture-ingestion pipeline yet; fixtures arrive in Release 0.2.
- Diagnosis, probe, planning, policy, and certificate schemas are defined but no
  diagnosis or execution engine consumes them yet.
- Transition rules are deterministic and do not yet model probabilistic
  behavior, controller retry backoff, or stochastic latency.
- Django executes bounded simulations synchronously.
- The UI graph uses a compact deterministic layout suitable for the current
  basis rather than a fleet-scale graph engine.
