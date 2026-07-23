# Built-in Release 0.5 knowledge packs

Every subdirectory contains one declarative `pack.yaml`. The packs are loaded
through `PackManager`; they are not Python modules.

| Pack | Dependencies | Main semantic surfaces |
|---|---|---|
| generic-kubernetes | none | generic classification, redaction, basis coverage |
| docker-host | generic-kubernetes | Docker runtime lifecycle |
| kind | generic-kubernetes, docker-host | Kind control-plane evidence and lifecycle |
| k3s | generic-kubernetes | k3s service evidence and maintenance |
| coredns | generic-kubernetes | DNS workload health and recovery |
| ingress-nginx | generic-kubernetes | ingress-controller health and recovery |
| argocd | generic-kubernetes | GitOps ownership, health, evidence, refresh |
| postgres | generic-kubernetes | database readiness and guarded restart |
| redis | generic-kubernetes | cache readiness and guarded restart |
| django | generic-kubernetes, postgres, redis | service dependencies and recovery |
| celery | generic-kubernetes, redis | worker dependencies and recovery |

Validate the entire set with:

```bash
kubeops pack validate
```

Resolve a dependency closure with:

```bash
kubeops pack resolve kind
```
