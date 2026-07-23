from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="ScenarioFamilyRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("family_id", models.CharField(max_length=255, unique=True)),
                ("version", models.CharField(max_length=64)),
                ("title", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                ("parent_family_id", models.CharField(blank=True, max_length=255, null=True)),
                ("content_hash", models.CharField(max_length=64)),
                ("payload", models.JSONField()),
                ("source_path", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["family_id"]},
        ),
        migrations.CreateModel(
            name="ScenarioRunRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("run_id", models.CharField(max_length=255, unique=True)),
                ("scenario_id", models.CharField(max_length=255)),
                ("family_id", models.CharField(max_length=255)),
                ("status", models.CharField(max_length=32)),
                ("scenario_payload", models.JSONField()),
                ("run_payload", models.JSONField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="ArtifactRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("artifact_id", models.CharField(max_length=255, unique=True)),
                ("artifact_type", models.CharField(max_length=64)),
                ("content_hash", models.CharField(max_length=64)),
                ("media_type", models.CharField(max_length=128)),
                ("storage_path", models.TextField()),
                ("derived_from", models.JSONField(default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="artifacts", to="api.scenariorunrecord")),
            ],
            options={"ordering": ["created_at"]},
        ),
        migrations.CreateModel(
            name="OperationEventRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sequence", models.PositiveIntegerField()),
                ("event_type", models.CharField(max_length=128)),
                ("occurred_at_seconds", models.PositiveIntegerField()),
                ("payload", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="api.scenariorunrecord")),
            ],
            options={"ordering": ["sequence"]},
        ),
        migrations.AddIndex(
            model_name="scenariorunrecord",
            index=models.Index(fields=["family_id", "created_at"], name="api_scenari_family__bb8f15_idx"),
        ),
        migrations.AddConstraint(
            model_name="operationeventrecord",
            constraint=models.UniqueConstraint(fields=("run", "sequence"), name="unique_run_event_sequence"),
        ),
    ]
