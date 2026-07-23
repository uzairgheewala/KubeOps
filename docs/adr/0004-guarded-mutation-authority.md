# ADR 0004: Guarded mutation authority

- Status: Accepted
- Release: 0.4

## Context

Release 0.3 can diagnose incidents and recommend read-only probes. The next
step requires executing lifecycle and recovery actions, but allowing diagnoses,
LLM output, arbitrary scripts, or the web API to mutate a cluster directly
would collapse planning, authorization, execution, and verification into one
unsafe authority boundary.

## Decision

KubeOps adopts a typed, multi-gate mutation architecture.

1. Every mutation is an `ActionInstance` of a registered
   `ActionTypeDefinition`.
2. A lifecycle or recovery planner may propose actions but cannot authorize
   them.
3. An independent policy engine evaluates each concrete action.
4. Required approvals, target fingerprint, capabilities, mutation budget, risk,
   target scope, and checkpoint requirements are evaluated before execution.
5. Executors are registered adapters; no unrestricted shell action exists.
6. Operation state, approvals, receipts, checkpoints, and events are persisted.
7. Recovery is certified from semantic verification, not process exit status.
8. Dry-run and simulation never receive an authoritative `recovered`
   certificate.
9. The Django control plane disables live execution by default through
   `KUBEOPS_LIVE_EXECUTION_ENABLED=0`.

## Consequences

### Positive

- Diagnosis confidence cannot bypass safety policy.
- Plans and policy decisions are independently auditable.
- Repeated and interrupted operations can be resumed safely.
- Low-risk local actions can become automated without creating a universal
  command-execution endpoint.
- Simulation remains useful without being confused with live proof.
- Provider packs can add depth behind stable contracts.

### Negative

- Adding a new action requires a definition, policy treatment, executor,
  verification, and tests.
- Some recoveries terminate as guidance-only or approval-required.
- The initial runtime has less breadth than a shell-script launcher.
- Live execution requires explicit administrator configuration in addition to
  ordinary policy authority.

## Rejected alternatives

### Let the diagnosis engine execute its recommended fix

Rejected because inference and authority are separate concerns.

### Store commands directly in runbooks

Rejected because arbitrary commands have no stable risk, idempotency,
precondition, rollback, or verification semantics.

### Treat successful command exit as recovery

Rejected because resource convergence and application serviceability may still
fail after a command succeeds.

### Mark simulations as recovered

Rejected because a modeled transition is not evidence about a live target.

### Enable live execution by default in development

Rejected because copied configuration and mistaken environment targeting can
turn a development default into a production hazard.
