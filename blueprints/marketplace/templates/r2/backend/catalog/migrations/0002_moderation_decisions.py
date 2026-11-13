"""Review receipts and default roles. No accounts or secrets are provisioned."""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def create_roles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    database = schema_editor.connection.alias
    for name in ("seller", "moderator"):
        Group.objects.using(database).get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]
    operations = [
        migrations.CreateModel(
            name="ModerationDecision",
            fields=[
                ("id", models.UUIDField(editable=False, primary_key=True, serialize=False)),
                ("content_revision", models.PositiveIntegerField()),
                ("content_sha256", models.CharField(max_length=71)),
                ("verdict", models.CharField(choices=[("APPROVE", "Approve"), ("REJECT", "Reject")], max_length=7)),
                ("reason", models.CharField(blank=True, max_length=300)),
                ("decided_at", models.DateTimeField(auto_now_add=True)),
                ("listing", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="moderation_decisions", to="catalog.listing")),
                ("moderator", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
            options={"constraints": [
                models.UniqueConstraint(fields=("listing", "content_revision"), name="one_moderation_verdict_per_revision"),
            ]},
        ),
        migrations.RunPython(create_roles, reverse_code=migrations.RunPython.noop),
    ]
