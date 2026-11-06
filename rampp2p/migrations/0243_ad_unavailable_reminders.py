from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rampp2p", "0242_add_performance_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="ad",
            name="unavailable_reminder_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="ad",
            name="unavailable_reminder_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="ad",
            name="unavailable_reminder_next_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name="ad",
            index=models.Index(
                fields=["unavailable_reminder_next_at"],
                name="rampp2p_ad_rem_next_idx",
            ),
        ),
    ]
