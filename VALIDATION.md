# KubeOps Release 1.0 validation record

## Validation status

Release 1.0 passed every executable and structural validation available in the build sandbox and was then verified again from a clean Release 0.5 checkout with the Release 1.0 delta overlaid.

The sandbox did not provide Docker, Helm, Django/DRF, pytest-django, or the real npm dependency graph, and outbound package installation was unavailable. Consequently, the repository's dependency-backed Django/PostgreSQL suite, actual Vite production bundle, and real `helm lint/template` execution could not be run locally. Those paths are present in GitHub Actions and use the pinned release dependencies. They are not represented below as locally executed successes.

## Executed locally

### Python operational kernel

- 102 unit tests passed.
- All retained Release 0.1–0.5 unit behavior passed.
- Python bytecode compilation passed across `packages`, `control_plane`, and `tests`.
- No unit-test failure, xfail, or skip was used to obtain the result.
- One pytest configuration warning was expected because pytest-django is not installed in the sandbox.

### Canonical architecture validator

`scripts/validate_release_10.py` passed with:

- 138 canonical JSON schemas.
- 190 built-in registry entries.
- 50 Django model projections.
- 50 migration-created model projections.
- 177 Python source files parsed.
- 42 YAML files parsed.
- 6 JSON files parsed.
- 17 Helm templates structurally checked.

The validator also checks:

- Version alignment across Python packages, UI, and Helm.
- Model/migration field correspondence.
- Helm template delimiters and referenced values.
- High-availability artifact-backend constraints.
- Required API/UI network-policy ports.
- Absence of sensitive local package-manager files.

### Knowledge-pack matrix

- All 11 built-in packs validated.
- All 2,047 non-empty pack selections resolved with dependency closure.
- No active selection produced a dependency cycle, blocked required dependency, or contribution collision.
- The complete runtime exposed the expected provider/component contribution catalog.

### Pack-aware environment replay

The full representative Kind/application fixture was collected 100 times with deterministic results:

- 36 entities.
- 32 relationships.
- Healthy generic cluster, CoreDNS, Ingress-NGINX, Argo CD, PostgreSQL, and Redis contracts.
- Intentionally unhealthy local-development, Django, and Celery contracts.
- Kind lifecycle plan resolved to the typed `kind.control-plane.start.v1` action.

### CLI and scripts

- The complete Release 1.0 CLI command tree loaded.
- Pack validation command completed.
- Fleet, access, executor, audit, retention, platform, security, and schedule command groups were present.
- All Bash scripts passed `bash -n`.
- No trailing whitespace was found in delivered text sources.

### TypeScript

- The complete TypeScript project-reference graph passed `tsc -b --pretty false`.
- Temporary external declaration shims were used only because npm packages were unavailable in the sandbox.
- The shims, generated `.tsbuildinfo` files, and `node_modules` are excluded from the release.
- The actual React/Vite production bundle remains a CI validation path, not a claimed local result.

### Security and production invariants

Unit/static validation covers:

- Hierarchical authorization and tenant isolation.
- Immutable agent identity.
- Content-idempotent distributed tasks.
- Capability, environment, executor, fingerprint, and capacity matching.
- Lease nonce and expiry enforcement.
- Deterministic governance timestamps.
- Audit-chain tamper detection.
- Legal-hold-aware retention.
- Maintenance windows and non-authoritative scheduling.
- HMAC and Ed25519 pack verification.
- Secret-material non-persistence.
- S3 content-addressed artifact behavior.
- Backup component/manifest verification.
- Restore enablement and backup-ID confirmation.
- Traversal-, link-, and device-safe archive extraction.
- Version-relative restore compatibility.

## CI validation paths included

The GitHub Actions workflow additionally installs all declared dependencies and runs:

- PostgreSQL-backed Django migrations.
- Every release seeder.
- Django system checks.
- Complete pytest suite, including integration tests.
- Ruff checks and coverage.
- Real npm install and Vite production build.
- Helm lint and template rendering.

## Release packaging validation

The final release process verifies:

- Delta contains only added/modified files.
- Repository-relative directory structure is preserved.
- No paths are deleted.
- Overlaying the delta on a clean Release 0.5 tree produces a byte-for-byte match with the sealed Release 1.0 source.
- Unit/static validations pass from the overlaid checkout.
- Every delta payload size and SHA-256 matches `DELTA_MANIFEST.json`.
- Every full-source payload hash matches `SOURCE_MANIFEST.json`.
- ZIP central-directory integrity passes.
- ZIP SHA-256 is emitted separately.

See `DELTA_MANIFEST.json` for exact final counts and hashes.
