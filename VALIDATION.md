# Release 0.2 validation record

## Executed in this delivery environment

### Python and core behavior

- 30 unit tests passed, including every retained Release 0.1 unit test.
- Python bytecode compilation passed for packages, control plane, and tests.
- All repository JSON, YAML, and YML files parsed successfully.
- Linux shell scripts passed `bash -n` syntax validation.

### Discovery and sanitization

- Fixture access validation passed for both included fixture sources.
- Degraded and healthy fixture collection each produced:
  - 26 sanitized `ResourceDocument` objects.
  - 26 canonical entities.
  - 30 typed relationships.
  - 26 observations.
  - Zero permission gaps.
- Secret values were removed while key names remained present.
- Collection artifacts were immutable and content addressed.

### Topology

Validated relationships include:

- Namespace containment.
- Deployment → ReplicaSet → Pod controller chains.
- Pod → Node scheduling.
- Pod → ServiceAccount identity.
- ConfigMap, Secret, and PVC references.
- Service selection.
- EndpointSlice membership.
- Ingress routing.
- PV/PVC/StorageClass binding.
- RoleBinding relationships.

An EndpointSlice label-path defect was found and fixed during validation.

### Operational health

- `cluster-observable.v1` evaluated healthy for both fixtures.
- `local-development-usable.v1` evaluated unhealthy for the degraded fixture.
- The same profile evaluated healthy for the healthy fixture.
- The degraded result correctly identified one underavailable Deployment and one
  unready Pod while preserving healthy independent checks.

### Snapshot diff

The degraded → healthy comparison produced:

- 0 added entities.
- 0 removed entities.
- 3 changed entities.
- 0 added relationships.
- 0 removed relationships.
- 1 changed relationship.

Repeated collection of the same fixture produced an empty structural diff.

### Randomized genericism checks

- 100 randomized environment definitions were compiled against healthy or degraded fixtures.
- All preserved 26 entities and 30 relationships.
- Repeated collection of the same source produced empty structural diffs.
- Profile assessments remained bound to the randomized environment identity.

### CLI

Executed successfully:

```text
environment validate
snapshot collect (degraded)
snapshot collect (healthy)
snapshot diff
profile evaluate (degraded)
profile evaluate (healthy)
```

### TypeScript

- The actual `tsc -b` project-reference graph passed for application and Vite
  configuration sources.
- The application and Vite project-reference graph was checked with temporary
  ambient declarations outside the delivered source tree. Normal installations
  use the pinned React/Vite packages and their official types.

## Dependency-gated checks

This sandbox does not contain Django, Django REST Framework, pytest-django,
Hypothesis, React, or Vite runtime packages, and its package mirror could not
supply them. Therefore the following were not executed here:

- Django migration application.
- Django/DRF integration tests.
- Actual API server startup.
- Hypothesis property suite.
- Vite production bundle and browser runtime.

The migration, integration tests, Docker setup, pinned dependencies, and CI
workflow are included. Execute the complete matrix after normal bootstrap:

```bash
./scripts/bootstrap.sh
./scripts/test.sh
```

or in GitHub Actions.

## Expected full validation matrix

```bash
ruff check packages control_plane tests
mypy packages/kubeops_core/kubeops_core
pytest --cov --cov-report=term-missing
cd ui && npm run build
```
