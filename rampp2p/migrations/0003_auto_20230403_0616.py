# Generated by Django 3.0.14 on 2023-04-03 06:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0002_auto_20230403_0553'),
    ]

    operations = [
        migrations.AlterField(
            model_name='peer',
            name='wallet_address',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]
