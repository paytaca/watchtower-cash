# Generated by Django 3.0.14 on 2025-03-20 02:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('paytacapos', '0059_auto_20250318_0825'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cashoutorder',
            name='sats_amount',
            field=models.BigIntegerField(editable=False, null=True),
        ),
    ]
