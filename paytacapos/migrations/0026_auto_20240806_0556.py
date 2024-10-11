# Generated by Django 3.0.14 on 2024-08-06 05:56

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('paytacapos', '0025_merchant_receiving_index'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='merchant',
            name='receiving_index',
        ),
        migrations.RemoveField(
            model_name='merchant',
            name='receiving_pubkey',
        ),
        migrations.AddField(
            model_name='posdevice',
            name='vault_pubkey',
            field=models.CharField(blank=True, max_length=70, null=True),
        ),
    ]
