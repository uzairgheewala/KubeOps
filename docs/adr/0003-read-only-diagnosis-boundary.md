# ADR 0003: Keep diagnosis active but read-only

- Status: Accepted
- Release: 0.3

## Context

KubeOps needs active investigation rather than passive dashboards. An operator
must be able to ask a diagnostic question, gather more evidence, and refine a
causal conclusion. However, combining evidence collection and remediation in
one unrestricted probe interface would make it impossible to reason clearly
about authority, risk, idempotency, and safety.

## Decision

Release 0.3 introduces active probes but restricts every built-in collector to
risk class `R0`.

A probe may:

- inspect an immutable snapshot;
- inspect topology and health projections;
- read already-sanitized resource state;
- compare snapshot history;
- produce normalized evidence facts;
- update hypotheses and certificates.

A probe may not:

- create, patch, or delete Kubernetes resources;
- restart or scale workloads;
- start or stop host processes;
- drain nodes;
- rotate credentials;
- trigger GitOps synchronization;
- perform recovery actions.

Collector planning and execution are therefore independent from the future
typed-action executor.

## Consequences

### Positive

- Diagnostic confidence cannot silently become execution authority.
- Every Release 0.3 incident can be replayed from sanitized artifacts.
- Evidence-gathering behavior is easy to test and reason about.
- Provider packs can add collectors without receiving mutation permissions.
- Recovery planning in Release 0.4 can consume a stable diagnosis certificate.

### Negative

- Some facts cannot be proven without an active network request or ephemeral
  debug workload in real environments.
- Release 0.3 may terminate with insufficient evidence more often than a
  privileged troubleshooting script.
- Mutating diagnostic techniques must wait for typed actions and policy review.

## Alternatives rejected

### Allow arbitrary shell probes

Rejected because command text does not provide stable risk, effect,
idempotency, or evidence contracts.

### Allow low-risk mutations in the collector SDK

Rejected because “low risk” is context-dependent and belongs in the policy and
typed-action architecture.

### Use an LLM to choose and run kubectl commands

Rejected because explanation generation is not a safe authority boundary and
cannot replace deterministic capability and policy checks.

## Follow-up

Release 0.4 may add separately registered typed actions with explicit effects,
preconditions, risk, approval, rollback, and verification. It must not expand
the Release 0.3 collector interface into a mutation path.
