import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('rampp2p', '0244_featurecontrol_p2p_maintenance')]

    operations = [
        migrations.CreateModel(
            name='RegistrationChallenge',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('account_type', models.CharField(choices=[('peer', 'Peer'), ('arbiter', 'Arbiter')], max_length=7)),
                ('payload_digest', models.CharField(max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField(db_index=True)),
                ('consumed_at', models.DateTimeField(blank=True, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='RegistrationRequestBucket',
            fields=[
                ('id', models.CharField(max_length=64, primary_key=True, serialize=False)),
                ('attempts', models.PositiveIntegerField(default=0)),
                ('expires_at', models.DateTimeField(db_index=True)),
            ],
        ),
    ]
