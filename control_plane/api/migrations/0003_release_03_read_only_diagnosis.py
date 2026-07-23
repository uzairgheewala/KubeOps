from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("api", "0002_release_02_read_only_intelligence")]

    operations = [
        migrations.CreateModel(
            name="IncidentRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("incident_id", models.CharField(max_length=255, unique=True)),
                ("profile_id", models.CharField(max_length=255)),
                ("title", models.CharField(max_length=512)),
                ("initial_symptom", models.TextField()),
                ("status", models.CharField(max_length=64)),
                ("certificate_status", models.CharField(blank=True, max_length=64, null=True)),
                ("confidence", models.FloatField(default=0.0)),
                ("payload", models.JSONField()),
                ("created_at", models.DateTimeField()),
                ("updated_at", models.DateTimeField()),
                ("persisted_at", models.DateTimeField(auto_now_add=True)),
                ("environment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="incidents", to="api.environmentrecord")),
                ("snapshot", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="incidents", to="api.environmentsnapshotrecord")),
            ],
            options={"ordering": ["-updated_at"]},
        ),
        migrations.CreateModel(
            name="EvidenceFactRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("evidence_id", models.CharField(max_length=255)),
                ("fact_type", models.CharField(max_length=255)),
                ("collector_id", models.CharField(max_length=255)),
                ("authority", models.CharField(max_length=32)),
                ("subject_ids", models.JSONField(default=list)),
                ("observed_at", models.DateTimeField()),
                ("payload", models.JSONField()),
                ("incident", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="evidence_facts", to="api.incidentrecord")),
            ],
            options={"ordering": ["fact_type", "evidence_id"]},
        ),
        migrations.CreateModel(
            name="HypothesisRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("hypothesis_id", models.CharField(max_length=255)),
                ("family_id", models.CharField(max_length=255)),
                ("status", models.CharField(max_length=32)),
                ("confidence", models.FloatField(default=0.0)),
                ("subject_ids", models.JSONField(default=list)),
                ("payload", models.JSONField()),
                ("incident", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="hypotheses", to="api.incidentrecord")),
            ],
            options={"ordering": ["-confidence", "family_id"]},
        ),
        migrations.CreateModel(
            name="ProbeRunRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("probe_run_id", models.CharField(max_length=255, unique=True)),
                ("probe_id", models.CharField(max_length=255)),
                ("intent_id", models.CharField(max_length=255)),
                ("status", models.CharField(max_length=32)),
                ("started_at", models.DateTimeField()),
                ("completed_at", models.DateTimeField()),
                ("payload", models.JSONField()),
                ("incident", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="probe_runs", to="api.incidentrecord")),
            ],
            options={"ordering": ["started_at"]},
        ),
        migrations.CreateModel(
            name="IncidentTimelineRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sequence", models.PositiveIntegerField()),
                ("event_type", models.CharField(max_length=128)),
                ("occurred_at", models.DateTimeField()),
                ("payload", models.JSONField(default=dict)),
                ("incident", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="timeline_entries", to="api.incidentrecord")),
            ],
            options={"ordering": ["sequence"]},
        ),
        migrations.CreateModel(
            name="DiagnosisCertificateRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("certificate_id", models.CharField(max_length=255, unique=True)),
                ("status", models.CharField(max_length=64)),
                ("confidence", models.FloatField(default=0.0)),
                ("issued_at", models.DateTimeField(blank=True, null=True)),
                ("payload", models.JSONField()),
                ("incident", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="diagnosis_certificate", to="api.incidentrecord")),
            ],
            options={"ordering": ["-issued_at"]},
        ),
        migrations.AddIndex(model_name="incidentrecord", index=models.Index(fields=["environment", "updated_at"], name="api_inciden_environ_8ac0b4_idx")),
        migrations.AddIndex(model_name="incidentrecord", index=models.Index(fields=["status", "updated_at"], name="api_inciden_status_906b40_idx")),
        migrations.AddIndex(model_name="incidentrecord", index=models.Index(fields=["profile_id", "certificate_status"], name="api_inciden_profile_76ba20_idx")),
        migrations.AddConstraint(model_name="evidencefactrecord", constraint=models.UniqueConstraint(fields=("incident", "evidence_id"), name="unique_incident_evidence")),
        migrations.AddConstraint(model_name="hypothesisrecord", constraint=models.UniqueConstraint(fields=("incident", "hypothesis_id"), name="unique_incident_hypothesis")),
        migrations.AddIndex(model_name="evidencefactrecord", index=models.Index(fields=["incident", "fact_type"], name="api_evidenc_inciden_2050cb_idx")),
        migrations.AddIndex(model_name="evidencefactrecord", index=models.Index(fields=["collector_id", "authority"], name="api_evidenc_collect_33234a_idx")),
        migrations.AddIndex(model_name="hypothesisrecord", index=models.Index(fields=["incident", "status"], name="api_hypothe_inciden_5792ee_idx")),
        migrations.AddIndex(model_name="hypothesisrecord", index=models.Index(fields=["family_id", "status"], name="api_hypothe_family__892f8c_idx")),
        migrations.AddIndex(model_name="proberunrecord", index=models.Index(fields=["incident", "started_at"], name="api_proberu_inciden_0b35ea_idx")),
        migrations.AddConstraint(model_name="incidenttimelinerecord", constraint=models.UniqueConstraint(fields=("incident", "sequence"), name="unique_incident_timeline_sequence")),
    ]
