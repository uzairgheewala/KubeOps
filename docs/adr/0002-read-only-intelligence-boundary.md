# ADR 0002: Read-only environment-intelligence boundary

## Status

Accepted.

## Context

Release 0.1 proved the operational IR, scenario-family compiler, deterministic
simulator, and UI against synthetic worlds. Release 0.2 needs real Kubernetes
evidence but should not yet carry the safety burden of cluster mutation.

## Decision

Release 0.2 introduces a common read-only discovery-source contract with fixture
and `kubectl` implementations. All source output is sanitized before entering
the canonical IR. The same entities, relationships, observations, invariants,
and artifacts used by simulation are used for live snapshots.

Environment observation and future execution authority remain distinct.
No environment API, CLI command, knowledge pack, or UI control in this release
can mutate the target.

PostgreSQL/Django store indexed projections and canonical payloads, while the
framework-independent core owns discovery normalization, topology, health,
diff, and artifacts.

## Consequences

### Positive

- Real environments can be inspected without destabilizing the safety model.
- Live incidents can be exported as sanitized deterministic fixtures.
- Generic topology and health semantics are validated before diagnosis and
  execution are added.
- Observer permissions can be audited independently from future executor
  capabilities.
- Release 0.1 remains a valid offline laboratory.

### Negative

- Some useful evidence still requires host access or active probes and remains
  unavailable.
- Synchronous `kubectl` collection is not the final fleet-scale architecture.
- The system can identify violated contracts but cannot yet explain root cause
  or repair them.

## Rejected alternatives

### Add restart and cleanup commands immediately

Rejected because it would couple unproven topology/health semantics to mutation
before action preconditions, policies, receipts, and verification exist.

### Store raw Kubernetes Secret payloads and redact only in the UI

Rejected because artifacts, logs, fixtures, and APIs would still contain secret
values. Redaction must precede canonicalization and persistence.

### Build fixture and live pipelines separately

Rejected because they would drift and invalidate fixture-based regression
claims. Both sources must feed one normalization and assessment pipeline.
