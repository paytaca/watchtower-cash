from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nostr', '0006_alter_nostrpubkey_last_active'),
    ]

    operations = [
        migrations.AddField(
            model_name='nostrpubkey',
            name='show_active_status',
            field=models.BooleanField(default=True, db_index=True),
        ),
    ]
