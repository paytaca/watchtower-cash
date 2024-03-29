# Generated by Django 3.0.14 on 2023-01-25 01:30

from django.db import migrations, models
import psqlextra.manager.manager


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0055_auto_20230109_2243'),
    ]

    operations = [
        migrations.CreateModel(
            name='TransactionMetaAttribute',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('txid', models.CharField(db_index=True, max_length=70)),
                ('wallet_hash', models.CharField(blank=True, db_index=True, default='', max_length=70)),
                ('system_generated', models.BooleanField(default=False)),
                ('key', models.CharField(db_index=True, max_length=50)),
                ('value', models.TextField()),
            ],
            options={
                'unique_together': {('txid', 'wallet_hash', 'key', 'system_generated')},
            },
            managers=[
                ('objects', psqlextra.manager.manager.PostgresManager()),
            ],
        ),
    ]
