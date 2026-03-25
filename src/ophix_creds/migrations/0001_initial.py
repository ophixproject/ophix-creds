from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("ophix_core", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Credential",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True)),
                ("description", models.TextField(blank=True, null=True)),
                ("secret_json", models.JSONField(default=dict)),
                ("enabled", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ("name",),
            },
        ),
        migrations.CreateModel(
            name="ClientCredential",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("enabled", models.BooleanField(default=True, help_text="Client can read this artifact (can_read).")),
                ("can_update", models.BooleanField(default=False, help_text="Client may overwrite this artifact.")),
                ("can_delete", models.BooleanField(default=False, help_text="Client may delete this artifact.")),
                ("can_share", models.BooleanField(default=False, help_text="Reserved: future client-driven sharing. Currently unused.")),
                ("notes", models.TextField(blank=True, null=True)),
                ("client", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="ophix_core.client")),
                ("credential", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="client_links", to="ophix_creds.credential")),
            ],
            options={
                "unique_together": {("client", "credential")},
            },
        ),
    ]
