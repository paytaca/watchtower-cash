# Generated by Django 3.0.14 on 2024-11-29 07:22

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0093_auto_20241125_0722'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cashnonfungibletoken',
            name='current_index',
            field=models.PositiveIntegerField(db_index=True),
        ),
        migrations.AlterField(
            model_name='cashnonfungibletoken',
            name='current_txid',
            field=models.CharField(db_index=True, max_length=70),
        ),
        migrations.AlterField(
            model_name='wallethistory',
            name='amount',
            field=models.FloatField(db_index=True, default=0),
        ),
    ]