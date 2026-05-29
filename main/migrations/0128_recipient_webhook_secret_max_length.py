from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0127_recipient_webhook_secret'),
    ]

    operations = [
        migrations.AlterField(
            model_name='recipient',
            name='webhook_secret',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
