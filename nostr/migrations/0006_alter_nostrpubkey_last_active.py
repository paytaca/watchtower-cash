from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nostr', '0005_add_covering_index'),
    ]

    operations = [
        migrations.AlterField(
            model_name='nostrpubkey',
            name='last_active',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
