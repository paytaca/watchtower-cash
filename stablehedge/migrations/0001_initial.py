# Generated by Django 3.0.14 on 2024-09-24 02:49

import django.contrib.postgres.fields.jsonb
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('anyhedge', '0013_auto_20240413_1340'),
    ]

    operations = [
        migrations.CreateModel(
            name='FiatToken',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('category', models.CharField(max_length=64)),
                ('genesis_supply', models.BigIntegerField(blank=True, null=True)),
                ('decimals', models.IntegerField()),
                ('currency', models.CharField(blank=True, max_length=5, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='RedemptionContract',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('address', models.CharField(max_length=100)),
                ('auth_token_id', models.CharField(max_length=64)),
                ('price_oracle_pubkey', models.CharField(max_length=70)),
                ('fiat_token', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='redemption_contracts', to='stablehedge.FiatToken')),
            ],
        ),
        migrations.CreateModel(
            name='RedemptionContractTransaction',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('transaction_type', models.CharField(max_length=15)),
                ('status', models.CharField(default='pending', max_length=10)),
                ('txid', models.CharField(blank=True, max_length=64, null=True)),
                ('utxo', django.contrib.postgres.fields.jsonb.JSONField()),
                ('result_message', models.CharField(blank=True, max_length=100, null=True)),
                ('retry_count', models.IntegerField(default=0)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('price_oracle_message', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='transactions', to='anyhedge.PriceOracleMessage')),
                ('redemption_contract', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='transactions', to='stablehedge.RedemptionContract')),
            ],
        ),
    ]
