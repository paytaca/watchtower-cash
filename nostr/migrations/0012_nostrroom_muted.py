from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nostr', '0011_nostrroom_group_id_lowercase'),
    ]

    operations = [
        migrations.AddField(
            model_name='nostrroom',
            name='muted',
            field=models.BooleanField(default=False),
        ),
    ]
