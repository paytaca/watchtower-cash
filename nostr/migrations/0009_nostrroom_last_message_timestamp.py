from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nostr', '0008_nostr_rooms_and_blocks'),
    ]

    operations = [
        migrations.AddField(
            model_name='nostrroom',
            name='last_message_timestamp',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
