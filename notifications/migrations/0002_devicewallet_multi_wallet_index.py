# Generated by Django 3.0.14 on 2024-04-01 03:00

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='devicewallet',
            name='multi_wallet_index',
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
