# KubeOps 1.0 production operations guide

## 1. Required external services

A production deployment requires:

- PostgreSQL 16 or a compatible managed PostgreSQL service.
- A Kubernetes cluster and ingress/TLS implementation.
- A Kubernetes Secret containing the Django secret key and database URL.
- S3-compatible object storage when running more than one API replica.
- A trusted Ed25519 public key or an explicitly accepted HMAC key for pack verification.
- A separate backup target for PostgreSQL and object-store data.

KubeOps does not persist raw secret values through its `SecretReference` model. Use workload identity, external-secret injection, or Kubernetes Secrets for runtime credentials.

## 2. Production defaults

Keep these values disabled until their corresponding workflows have been tested:

```text
KUBEOPS_LIVE_EXECUTION_ENABLED=0
KUBEOPS_RETENTION_APPLY_ENABLED=0
KUBEOPS_RESTORE_ENABLED=0
KUBEOPS_ALLOW_ANONYMOUS_READ=0
KUBEOPS_AUDIT_REQUIRED=1
```

`DJANGO_SECRET_KEY` must be nondefault and at least 32 characters. `DJANGO_ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS` must match the deployed host. Enable Django's HTTPS redirect and HSTS settings only after TLS forwarding is confirmed.

## 3. Build images

From the repository root:

```powershell
$version = "1.0.0"
docker build -f control_plane/Dockerfile -t ghcr.io/<org>/kubeops-api:$version .
docker build -f ui/Dockerfile -t ghcr.io/<org>/kubeops-ui:$version ./ui
docker push ghcr.io/<org>/kubeops-api:$version
docker push ghcr.io/<org>/kubeops-ui:$version
```

The API image runs Gunicorn as a nonroot user. The UI image builds the React application and serves static assets from unprivileged Nginx on port 8080.

## 4. Prepare the namespace and secret

```powershell
kubectl create namespace kubeops
kubectl -n kubeops create secret generic kubeops-secrets `
  --from-literal=django-secret-key='<random-32+-character-secret>' `
  --from-literal=database-url='postgresql://user:password@host:5432/kubeops' `
  --from-file=pack-trust-public-key='./release-public-key.pem'
```

The private Ed25519 signing key should remain outside the cluster. `pack-trust-secret` is optional and intended primarily for controlled HMAC workflows.

## 5. Configure high availability

For one API replica, the file artifact backend may use the chart PVCs. For multiple replicas or HPA, configure object storage:

```powershell
helm upgrade --install kubeops ./deploy/helm/kubeops `
  --namespace kubeops `
  --set api.image.repository=ghcr.io/<org>/kubeops-api `
  --set api.image.tag=1.0.0 `
  --set ui.image.repository=ghcr.io/<org>/kubeops-ui `
  --set ui.image.tag=1.0.0 `
  --set api.replicas=3 `
  --set config.artifactBackend=s3 `
  --set config.artifactS3Bucket=kubeops-artifacts `
  --set config.artifactS3Region=us-west-2 `
  --set ingress.host=kubeops.example.com `
  --set config.allowedHosts=kubeops.example.com `
  --set config.corsAllowedOrigins=https://kubeops.example.com
```

Provide bucket credentials through the platform workload-identity mechanism or external-secret integration. The chart validation rejects API autoscaling while the artifact backend is local file storage.

## 6. Database migration and bootstrap

The Helm migration hook runs:

1. Django migrations.
2. Release 0.1/0.2/0.4/0.5 catalog seeders.
3. Release 1.0 organization, workspace, governance, maintenance-window, fleet, trust, and pack projections.

The seeders are idempotent. Production CI should run migrations against an ephemeral PostgreSQL service before image promotion.

## 7. Authentication and tenancy

Create an administrator and token:

```powershell
kubectl -n kubeops exec deploy/kubeops-api -- python control_plane/manage.py createsuperuser
kubectl -n kubeops exec deploy/kubeops-api -- python control_plane/manage.py drf_create_token <username>
```

Enter the token, organization ID, and workspace ID in the login panel. Browser credentials remain in memory and are lost on refresh. Every request includes explicit tenant-scope headers.

Create narrower role grants for operators, viewers, auditors, approvers, and executor identities rather than sharing a superuser token.

## 8. Distributed executors

The Helm executor deployment registers one agent and advertises only the configured executor IDs and capabilities. Default values permit dry-run, simulation, and wait actions.

Before enabling live actions:

- Create a separate workspace-scoped executor identity.
- Restrict its Kubernetes RBAC.
- Configure exact supported executor IDs.
- Configure environment allowlists and maximum concurrency.
- Confirm target fingerprints.
- Test lease expiry and agent restart.
- Keep `KUBEOPS_LIVE_EXECUTION_ENABLED=0` until all checks pass.

An agent ID cannot be rebound to a different tenant or public identity. Repeated task submission is content-idempotent; a conflicting payload is rejected.

## 9. Scheduling and maintenance windows

The scheduler CronJob evaluates durable scheduled requests. It can mark a request ready or materialize a normal operation/fleet plan. It cannot approve or execute that operation.

Use maintenance windows to restrict allowed operation classes and targets. Always set deadlines for nontrivial maintenance so stale requests expire rather than execute in a later window.

## 10. Audit, limits, and retention

- Keep `KUBEOPS_AUDIT_REQUIRED=1` in production.
- Verify the audit chain periodically and export signed/immutable evidence to external storage.
- Define workspace rate and concurrency limits before enabling live execution.
- Run retention in dry-run mode and review legal holds before setting `KUBEOPS_RETENTION_APPLY_ENABLED=1`.
- Store audit exports outside the same failure domain as the control plane.

## 11. Knowledge-pack trust

Production workspaces should use strict trust policies with Ed25519 signatures. Resolution must fail closed when a required signature is missing, expired, signed by an untrusted key, or does not match the canonical manifest hash.

A trusted pack contributes schemas, classifiers, collectors, templates, and typed actions. It still does not grant the executor capability or approval needed to run an action.

## 12. Backups

The backup CronJob is concurrency-limited. A valid backup contains:

- PostgreSQL logical dump.
- Configuration archive.
- Local artifact archive or proof that the external artifact backup is verified.
- Manifest with size and SHA-256 for every component.

After each backup:

1. Verify the manifest.
2. Replicate the backup outside the cluster.
3. Record recovery-point age.
4. Periodically rehearse restore in a disposable environment.

Do not call a backup recovery-ready merely because the CronJob succeeded.

## 13. Restore

Restore is disabled by default. First produce and review a plan:

```powershell
python control_plane/manage.py restore_platform_backup <path-to-manifest>
```

For a destructive restore, set `KUBEOPS_RESTORE_ENABLED=1` only for the restore job and provide the exact backup ID confirmation expected by the command. Restore re-verifies all components and rejects unsafe archive members before changing state.

Perform restores with normal API/executor/scheduler traffic stopped. Re-run migrations, seeders, audit verification, pack verification, and environment health after restore.

## 14. Upgrade process

Before upgrading:

- Create and verify a fresh backup.
- Run the upgrade-readiness endpoint or CLI.
- Verify pack compatibility and signatures.
- Render/lint the Helm chart in CI.
- Run migrations against a copy of production data when possible.
- Confirm executor agents support the target action catalog.
- Confirm object-store access from every API replica.

Upgrade the migration job first, then API, executors, scheduler, and UI. Keep live execution disabled during schema migrations unless an approved maintenance procedure requires otherwise.

## 15. Failure recovery

If the API is unavailable:

1. Check PostgreSQL, API pod, ingress, and artifact backend independently.
2. Preserve logs and audit state before restarting.
3. Confirm no active leases are still valid before dispatch recovery.
4. Restore only from a freshly verified manifest.

If an executor disappears, its leases expire and tasks follow their configured retry or terminal-failure policy. Do not manually mark a task complete without an authoritative action receipt.
