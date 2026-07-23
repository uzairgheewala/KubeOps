# ADR 0005: Use declarative knowledge packs instead of unrestricted plugins

- Status: accepted
- Release: 0.5

## Context

KubeOps needs provider- and component-specific semantics, but embedding Kind,
k3s, CoreDNS, Argo CD, PostgreSQL, Django, and similar behavior directly into
the kernel would make generic reasoning progressively less coherent. A normal
Python plugin system would create an equally serious problem: installing
operational knowledge would become equivalent to granting arbitrary code
execution inside a highly privileged control plane.

## Decision

Use independently versioned declarative knowledge packs.

A pack may contribute only canonical typed objects and references to handlers
or executors already registered by trusted KubeOps code. Pack resolution occurs
before contributions enter runtime registries.

Entities preserve a generic type lineage when specialized by a pack.

## Consequences

### Positive

- Provider/component knowledge evolves independently.
- The operational kernel remains stable.
- Pack behavior is inspectable, hashable, testable, and exportable.
- Compatibility and dependency failures are explicit.
- Contribution collisions cannot silently override behavior.
- Generic and specialized reasoning can coexist.
- Installing data does not automatically execute code.

### Negative

- The initial handler vocabulary is intentionally limited.
- Some integrations cannot be expressed until a trusted generic handler is
  added to the kernel.
- Packs cannot ship novel executable collectors without a future sandboxed
  adapter mechanism.
- Manifest schemas require versioned evolution discipline.

## Rejected alternatives

### Hard-code every integration

Rejected because it couples the kernel release cadence to every provider and
component and eventually turns generic engines into conditional branches.

### Import arbitrary Python entry points

Rejected because pack installation would grant arbitrary process authority and
make manifests non-auditable as the complete behavioral contract.

### Permit shell commands in manifests

Rejected because it bypasses typed actions, capability declarations, policy,
parameter validation, and executor restrictions.

### Replace generic entity types with specialized types

Rejected after fixture validation showed generic profiles becoming unmatched.
Type lineage now preserves ancestor semantics.
