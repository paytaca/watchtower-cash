# Generated by Django 3.0.14 on 2025-03-26 01:26

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0101_auto_20250324_0655'),
        ('paytacapos', '0060_auto_20250320_0248'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cashouttransaction',
            name='transaction',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='main.Transaction'),
        ),
        migrations.AlterField(
            model_name='cashouttransaction',
            name='wallet_history',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='main.WalletHistory'),
        ),
    ]
