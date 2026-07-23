# KubeOps Release 0.4 architecture

## 1. Purpose

Release 0.4 introduces a guarded transition from operational reasoning to
bounded action. It does not let diagnosis directly execute commands. Instead,
it separates the path into independently inspectable contracts:

```text
health / diagnosis
        ↓
lifecycle objective
        ↓
recovery plan
        ↓
policy decisions
        ↓
approvals and checkpoints
        ↓
typed executor
        ↓
semantic verification
        ↓
mode-aware certificate
```

Each boundary can deny or stop progression.

## 2. Lifecycle model

A lifecycle profile declares the desired transition for an environment class.
It contains an acyclic graph of stages. Each stage contains an acyclic graph of
typed action templates.

A template supplies:

- action type;
- target selector;
- parameter template;
- intra-stage dependencies;
- applicability and skip predicates;
- optional risk override;
- optionality metadata.

The compiler binds templates to a concrete `EnvironmentSnapshot`. It omits
inapplicable work, expands selectors, renders resource parameters, and connects
each stage to terminal actions from prerequisite stages.

Startup and shutdown are therefore ordinary goal-directed plans rather than
hard-coded special runtimes.

## 3. Action catalog

`ActionTypeDefinition` is the stable authority unit. It describes what an
action means independently of one concrete target.

```text
ActionTypeDefinition
  identity
  parameter schema
  preconditions
  expected effects
  possible side effects
  required capabilities
  supported modes
  executor ID
  default risk
  retries and timeout
  verification
  rollback type
```

`ActionInstance` binds that definition into a plan with targets, parameters,
dependencies, risk, idempotency key, stage, checkpoint need, and metadata.

The runtime never accepts an unregistered command as a plan action.

## 4. Independent policy evaluation

Policy receives:

- concrete action;
- registered action definition;
- environment class;
- actual and expected target fingerprints;
- runtime capabilities;
- current mutation count;
- approvals;
- break-glass state.

It produces one of:

- `allow`;
- `approval_required`;
- `deny`.

The decision records reasons, capability gaps, approval count, checkpoint need,
and risk rank. The planner cannot override it.

Approval quorum is identity-based. Duplicate records from one approver count
once. Expired approvals are ignored. Any active applicable rejection changes
the outcome to `deny`.

## 5. Executor boundary

Executors implement a narrow protocol:

```text
execute(action, definition, execution_context, attempt) -> ActionReceipt
```

The context carries mode, environment identity, command allowlists, working
directory, environment variables, simulation world, and metadata.

Initial executor classes are:

- dry run;
- simulation;
- wait;
- local process;
- port-forward;
- safe generic command;
- Kubernetes-safe command.

The local process executor uses argument arrays without a shell. The
Kubernetes Job cleanup path performs a read-only preflight, requires terminal
state, refuses active Jobs, and treats `NotFound` as satisfaction of the desired
absence postcondition.

## 6. Durable operation state machine

`OperationRun` is the aggregate root. The file store writes it atomically and
can reload it after interruption.

Execution proceeds by topological readiness:

1. authorize every action;
2. stop if any action is denied;
3. wait if approval is missing;
4. checkpoint before required elevated action;
5. skip completed matching idempotency keys;
6. execute ready actions within policy concurrency;
7. persist each receipt and event;
8. stop, pause, continue, or rollback according to each stage policy;
9. evaluate verification conditions;
10. issue a certificate.

The initial runtime is conservative and primarily sequential, even though the
plan and policy retain concurrency metadata for future releases.

## 7. Checkpoints and resumption

A checkpoint records:

- completed action IDs;
- pending action IDs;
- failed action IDs;
- canonical world state;
- state hash;
- resumability.

Resume reloads the journal, clears transient pause/failure fields, reauthorizes
under current policy and approvals, and uses persisted receipts and
idempotency keys to avoid replaying completed effects.

## 8. Rollback

An action type may point to a registered rollback action type. Rollback walks
completed receipts in reverse order, compiles bounded rollback actions, records
all rollback attempts, and issues a `rollback_completed` certificate.

Rollback completion does not claim the original objective was restored. Its
certificate retains the residual risk that target invariants remain unmet.

## 9. Verification

The verification engine evaluates `VerificationCondition` predicates against
the post-execution canonical world and relationship graph.

Conditions are grouped by semantic level:

- action completion;
- resource convergence;
- dependency restoration;
- semantic health;
- end-to-end objective;
- stability;
- side-effect guard.

A protected side-effect guard can fail an otherwise successful transition.

## 10. Certificate trust

Certificate status depends on verification and execution authority.

```text
dry run                  → partially_recovered
simulation               → partially_recovered
live + verified          → recovered
live + failed verify     → recovery_failed
rollback path completed  → rollback_completed
```

This avoids representing a model result as proof about a live system.

## 11. Persistence and artifacts

Django stores relational query projections while the canonical operation
payload remains authoritative. The append-oriented artifacts preserve plan,
policy, approvals, receipts, timeline, checkpoints, verification, certificate,
and a derivation manifest.

The operation manifest uses the persisted `updated_at_iso` revision rather than
wall-clock artifact-build time, so rebuilding an unchanged operation produces
the same content-addressed IDs.

## 12. UI architecture

The operation workbench coordinates:

- plan preview;
- stage DAG;
- policy decisions;
- approval gates;
- execution receipts;
- checkpoints;
- verification;
- certificate;
- timeline;
- artifact lineage.

Simulation and dry-run authority are labeled prominently. The control plane
also enforces the boundary server-side.

## 13. Future extension points

Release 0.5 can add provider-specific packs without changing the operation
kernel. A pack can contribute action definitions, executor implementations,
lifecycle templates, verification checks, safety defaults, and live scenario
fixtures while preserving the same policy and certificate contracts.
