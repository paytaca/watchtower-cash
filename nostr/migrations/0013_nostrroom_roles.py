from django.contrib.postgres.fields import JSONField
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nostr', '0012_nostrroom_muted'),
    ]

    operations = [
        migrations.AddField(
            model_name='nostrroom',
            name='owner',
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name='nostrroom',
            name='admins',
            field=JSONField(blank=True, default=list),
        ),
    ]
