from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0126_add_address_composite_index'),
    ]

    operations = [
        migrations.AddField(
            model_name='recipient',
            name='webhook_secret',
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
    ]
