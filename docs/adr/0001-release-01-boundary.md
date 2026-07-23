# ADR 0001: Release 0.1 boundary

## Status
Accepted.

## Decision
Release 0.1 is simulation-first. It implements the canonical operational IR,
registries, deterministic simulator, scenario-family compiler, append-oriented
run artifacts, Django API, CLI, and React Scenario Lab.

It deliberately excludes live Kubernetes discovery and all cluster mutation.
The same IR and run contracts must be used later by fixture and live modes.

## Consequences
- Architecture can be changed before operational authority is introduced.
- The UI can be developed against deterministic scenarios.
- Scenario families are validated as reusable generative models rather than
  hard-coded error handlers.
- Live-cluster support begins only after the metamodel and simulator prove
  stable.
