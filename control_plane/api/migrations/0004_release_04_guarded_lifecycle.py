from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("api", "0003_release_03_read_only_diagnosis")]

    operations = [
        migrations.CreateModel(
            name="LifecycleProfileRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("profile_id", models.CharField(max_length=255, unique=True)),
                ("version", models.CharField(max_length=64)),
                ("title", models.CharField(max_length=255)),
                ("operation_type", models.CharField(max_length=32)),
                ("target_operational_profile_id", models.CharField(max_length=255)),
                ("content_hash", models.CharField(max_length=64)),
                ("payload", models.JSONField()),
                ("source_path", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ], options={"ordering": ["profile_id"]},
        ),
        migrations.CreateModel(
            name="ExecutionPolicyRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("policy_id", models.CharField(max_length=255, unique=True)),
                ("title", models.CharField(max_length=255)),
                ("content_hash", models.CharField(max_length=64)),
                ("payload", models.JSONField()),
                ("source_path", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ], options={"ordering": ["policy_id"]},
        ),
        migrations.CreateModel(
            name="OperationRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("operation_id", models.CharField(max_length=255, unique=True)),
                ("operation_type", models.CharField(max_length=32)),
                ("objective_id", models.CharField(max_length=255)),
                ("status", models.CharField(max_length=64)),
                ("mode", models.CharField(max_length=32)),
                ("plan_id", models.CharField(max_length=255)),
                ("policy_id", models.CharField(blank=True, max_length=255, null=True)),
                ("certificate_status", models.CharField(blank=True, max_length=64, null=True)),
                ("payload", models.JSONField()),
                ("created_at", models.DateTimeField()),
                ("updated_at", models.DateTimeField()),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("persisted_at", models.DateTimeField(auto_now_add=True)),
                ("environment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="operations", to="api.environmentrecord")),
                ("incident", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="operations", to="api.incidentrecord")),
                ("snapshot", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="operations", to="api.environmentsnapshotrecord")),
            ], options={"ordering": ["-updated_at"]},
        ),
        migrations.CreateModel(
            name="OperationPolicyDecisionRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("decision_id", models.CharField(max_length=255)), ("action_id", models.CharField(max_length=255)),
                ("policy_id", models.CharField(max_length=255)), ("outcome", models.CharField(max_length=32)),
                ("payload", models.JSONField()),
                ("operation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="policy_decisions", to="api.operationrecord")),
            ], options={"ordering": ["action_id"]},
        ),
        migrations.CreateModel(
            name="OperationApprovalRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("approval_id", models.CharField(max_length=255, unique=True)),
                ("action_id", models.CharField(blank=True, max_length=255, null=True)),
                ("approver_id", models.CharField(max_length=255)), ("decision", models.CharField(max_length=16)),
                ("granted_at", models.DateTimeField()), ("payload", models.JSONField()),
                ("operation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="approvals", to="api.operationrecord")),
            ], options={"ordering": ["granted_at"]},
        ),
        migrations.CreateModel(
            name="ActionReceiptRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("receipt_id", models.CharField(max_length=255, unique=True)), ("action_id", models.CharField(max_length=255)),
                ("action_type_id", models.CharField(max_length=255)), ("executor_id", models.CharField(max_length=255)),
                ("status", models.CharField(max_length=32)), ("attempt", models.PositiveIntegerField(default=1)),
                ("started_at", models.DateTimeField()), ("completed_at", models.DateTimeField()),
                ("idempotency_key", models.CharField(blank=True, max_length=512, null=True)), ("payload", models.JSONField()),
                ("operation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="action_receipts", to="api.operationrecord")),
            ], options={"ordering": ["started_at", "receipt_id"]},
        ),
        migrations.CreateModel(
            name="OperationTimelineRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sequence", models.PositiveIntegerField()), ("event_type", models.CharField(max_length=128)),
                ("action_id", models.CharField(blank=True, max_length=255, null=True)), ("occurred_at", models.DateTimeField()),
                ("payload", models.JSONField(default=dict)),
                ("operation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="timeline_entries", to="api.operationrecord")),
            ], options={"ordering": ["sequence"]},
        ),
        migrations.CreateModel(
            name="ExecutionCheckpointRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("checkpoint_id", models.CharField(max_length=255, unique=True)), ("state_hash", models.CharField(max_length=64)),
                ("resumable", models.BooleanField(default=True)), ("created_at", models.DateTimeField()), ("payload", models.JSONField()),
                ("operation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="checkpoints", to="api.operationrecord")),
            ], options={"ordering": ["created_at"]},
        ),
        migrations.CreateModel(
            name="OperationVerificationRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("result_id", models.CharField(max_length=255, unique=True)), ("condition_id", models.CharField(max_length=255)),
                ("status", models.CharField(max_length=32)), ("payload", models.JSONField()),
                ("operation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="verification_results", to="api.operationrecord")),
            ], options={"ordering": ["condition_id"]},
        ),
        migrations.CreateModel(
            name="RecoveryCertificateRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("certificate_id", models.CharField(max_length=255, unique=True)), ("status", models.CharField(max_length=64)),
                ("payload", models.JSONField()), ("created_at", models.DateTimeField(auto_now_add=True)),
                ("operation", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="recovery_certificate", to="api.operationrecord")),
            ], options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(model_name="operationpolicydecisionrecord", constraint=models.UniqueConstraint(fields=("operation", "decision_id"), name="unique_operation_policy_decision")),
        migrations.AddConstraint(model_name="operationtimelinerecord", constraint=models.UniqueConstraint(fields=("operation", "sequence"), name="unique_operation_timeline_sequence")),
        migrations.AddIndex(model_name="operationrecord", index=models.Index(fields=["environment", "updated_at"], name="api_operati_environ_2de993_idx")),
        migrations.AddIndex(model_name="operationrecord", index=models.Index(fields=["status", "updated_at"], name="api_operati_status_13887b_idx")),
        migrations.AddIndex(model_name="operationrecord", index=models.Index(fields=["operation_type", "status"], name="api_operati_operati_3b1caf_idx")),
        migrations.AddIndex(model_name="actionreceiptrecord", index=models.Index(fields=["operation", "action_id"], name="api_actionr_operati_1baae1_idx")),
        migrations.AddIndex(model_name="actionreceiptrecord", index=models.Index(fields=["idempotency_key", "status"], name="api_actionr_idempot_47bfb8_idx")),
    ]
