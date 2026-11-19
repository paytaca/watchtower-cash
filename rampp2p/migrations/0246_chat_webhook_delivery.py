from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('rampp2p', '0245_registration_protection')]

    operations = [
        migrations.CreateModel(
            name='ChatWebhookDelivery',
            fields=[
                ('message_id', models.BigIntegerField(primary_key=True, serialize=False)),
                ('expires_at', models.DateTimeField(db_index=True)),
            ],
        ),
    ]
