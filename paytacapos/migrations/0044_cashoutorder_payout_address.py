# Generated by Django 3.0.14 on 2025-02-24 03:03

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('paytacapos', '0043_auto_20250220_0630'),
    ]

    operations = [
        migrations.AddField(
            model_name='cashoutorder',
            name='payout_address',
            field=models.CharField(max_length=255, null=True),
        ),
    ]
