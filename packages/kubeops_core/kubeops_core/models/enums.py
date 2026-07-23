from enum import StrEnum


class OperationalPlane(StrEnum):
    EXTERNAL = "external"
    HOST = "host"
    RUNTIME = "runtime"
    CONTROL_PLANE = "control_plane"
    NODE = "node"
    PLATFORM = "platform"
    WORKLOAD = "workload"
    APPLICATION = "application"
    OPERATIONAL_TOOLING = "operational_tooling"


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"
    PENDING = "pending"


class InvariantFamily(StrEnum):
    EXISTENCE = "existence"
    IDENTITY_RESOLUTION = "identity_resolution"
    STRUCTURAL = "structural"
    CONFIGURATION = "configuration"
    COMPATIBILITY = "compatibility"
    REACHABILITY = "reachability"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    CAPACITY = "capacity"
    PLACEMENT = "placement"
    LIFECYCLE_PROGRESS = "lifecycle_progress"
    READINESS = "readiness"
    LIVENESS = "liveness"
    ORDERING = "ordering"
    IDEMPOTENCY = "idempotency"
    CONSISTENCY = "consistency"
    FRESHNESS = "freshness"
    DURABILITY = "durability"
    ISOLATION = "isolation"
    QUORUM = "quorum"
    PERFORMANCE = "performance"
    OBSERVABILITY = "observability"
    RECOVERABILITY = "recoverability"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class DisturbanceMechanism(StrEnum):
    OMISSION = "omission"
    COMMISSION = "commission"
    CORRUPTION = "corruption"
    CRASH = "crash"
    HANG = "hang"
    DELAY = "delay"
    LOSS = "loss"
    DUPLICATION = "duplication"
    REORDERING = "reordering"
    PARTITION = "partition"
    DRIFT = "drift"
    EXPIRATION = "expiration"
    EXHAUSTION = "exhaustion"
    CONTENTION = "contention"
    MISBINDING = "misbinding"
    POLICY_MISMATCH = "policy_mismatch"
    VERSION_SKEW = "version_skew"
    EXTERNAL_CONTRACT = "external_contract"


class TemporalForm(StrEnum):
    INSTANTANEOUS = "instantaneous"
    TRANSIENT = "transient"
    PERSISTENT = "persistent"
    INTERMITTENT = "intermittent"
    PERIODIC = "periodic"
    PROGRESSIVE = "progressive"
    LATENT = "latent"
    DELAYED_EFFECT = "delayed_effect"
    CASCADING = "cascading"
    FLAPPING = "flapping"
    RECOVERY_INDUCED = "recovery_induced"
    CONCURRENT = "concurrent"


class ObservationProfileKind(StrEnum):
    FULL = "full"
    PARTIAL = "partial"
    DELAYED = "delayed"
    STALE = "stale"
    CONTRADICTORY = "contradictory"


class RunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
