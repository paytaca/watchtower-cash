from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nostr', '0009_nostrroom_last_message_timestamp'),
    ]

    operations = [
        migrations.AddField(
            model_name='nostrroom',
            name='nostr_group_id',
            field=models.CharField(blank=True, db_index=True, max_length=64, null=True),
        ),
    ]
