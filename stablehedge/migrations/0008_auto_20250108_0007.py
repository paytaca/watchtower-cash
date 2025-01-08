# Generated by Django 3.0.14 on 2025-01-08 00:07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stablehedge', '0007_treasurycontractshortpositionrule'),
    ]

    operations = [
        migrations.AddField(
            model_name='redemptioncontracttransaction',
            name='trade_size_in_satoshis',
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='redemptioncontracttransaction',
            name='trade_size_in_token_units',
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='redemptioncontracttransaction',
            name='status',
            field=models.CharField(db_index=True, default='pending', max_length=10),
        ),
        migrations.AlterField(
            model_name='redemptioncontracttransaction',
            name='transaction_type',
            field=models.CharField(db_index=True, max_length=15),
        ),
    ]
