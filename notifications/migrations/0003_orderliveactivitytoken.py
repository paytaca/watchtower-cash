
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0002_devicewallet_multi_wallet_index'),
    ]

    operations = [
        migrations.CreateModel(
            name='OrderLiveActivityToken',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order_id', models.BigIntegerField()),
                ('token', models.CharField(max_length=512)),
                ('platform', models.CharField(choices=[('ios', 'iOS'), ('android', 'Android')], max_length=16)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'unique_together': {('order_id', 'token', 'platform')},
            },
        ),
    ]
