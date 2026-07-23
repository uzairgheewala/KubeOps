# KubeOps 1.0 production deployment

This directory complements the chart at `deploy/helm/kubeops`. The chart deploys the Gunicorn API, static Nginx UI, migration/seed hook, distributed executor, scheduler, backup job, ingress, services, disruption budgets, network policy, and optional autoscaling.

Read [`../../docs/production-operations.md`](../../docs/production-operations.md) before enabling live execution, destructive retention, or restore.

## Minimum secure installation

Provision PostgreSQL first and create the namespace and secret. Do not place raw credentials in `values.yaml`.

```powershell
kubectl create namespace kubeops
kubectl -n kubeops create secret generic kubeops-secrets `
  --from-literal=django-secret-key='<random-32+-character-secret>' `
  --from-literal=database-url='postgresql://user:password@postgres.example:5432/kubeops' `
  --from-file=pack-trust-public-key='./release-public-key.pem'

helm upgrade --install kubeops ./deploy/helm/kubeops `
  --namespace kubeops `
  --set ingress.host=kubeops.example.com `
  --set config.allowedHosts=kubeops.example.com `
  --set config.corsAllowedOrigins=https://kubeops.example.com
```

The chart defaults to:

- Anonymous reads disabled.
- Audit required.
- Live execution disabled.
- Retention application disabled.
- Restore disabled.
- Executor restricted to dry-run, simulation, and wait adapters.

## High availability

The default file backend is valid only for one API replica. Before horizontal scaling, configure a shared S3-compatible artifact store:

```powershell
helm upgrade --install kubeops ./deploy/helm/kubeops `
  --namespace kubeops `
  --set api.replicas=3 `
  --set config.artifactBackend=s3 `
  --set config.artifactS3Bucket=kubeops-artifacts `
  --set config.artifactS3Region=us-west-2
```

Use workload identity or an external-secret mechanism for object-store credentials. The chart rejects autoscaling with the local file artifact backend.

## TLS hardening

The chart terminates TLS through ingress. Once proxy forwarding is confirmed, set:

```powershell
--set config.secureSslRedirect=1 `
--set config.secureHstsSeconds=31536000 `
--set config.secureHstsIncludeSubdomains=1
```

Set `secureHstsPreload=1` only after the domain is intentionally eligible for browser preload behavior.

## Validation in CI

Release CI installs the declared Python and UI dependencies, runs migrations and every seeder against PostgreSQL, executes the complete test suite, builds the UI, runs the Release 1.0 static validator, and lints/renders the Helm chart.
