# Generated by Django 3.0.14 on 2021-07-08 01:21

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0033_token_logo_url'),
    ]

    operations = [
        migrations.AlterField(
            model_name='wallethistory',
            name='txid',
            field=models.CharField(db_index=True, max_length=70),
        ),
    ]
