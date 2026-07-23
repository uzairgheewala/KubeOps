from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0004_release_04_guarded_lifecycle")]

    operations = [
        migrations.CreateModel(
            name="KnowledgePackRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("pack_id", models.CharField(max_length=255, unique=True)),
                ("version", models.CharField(max_length=64)),
                ("title", models.CharField(max_length=255)),
                ("pack_kind", models.CharField(max_length=32)),
                ("state", models.CharField(default="discovered", max_length=32)),
                ("enabled", models.BooleanField(default=True)),
                ("source_path", models.TextField(blank=True)),
                ("manifest_hash", models.CharField(max_length=64)),
                ("contribution_counts", models.JSONField(default=dict)),
                ("capabilities", models.JSONField(default=list)),
                ("payload", models.JSONField()),
                ("validation_issues", models.JSONField(default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["pack_kind", "pack_id"]},
        ),
        migrations.AddIndex(model_name="knowledgepackrecord", index=models.Index(fields=["state", "enabled"], name="api_knowled_state_43e7e4_idx")),
        migrations.AddIndex(model_name="knowledgepackrecord", index=models.Index(fields=["pack_kind", "pack_id"], name="api_knowled_pack_ki_f0e213_idx")),
    ]
