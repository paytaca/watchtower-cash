# Generated by Django 3.0.14 on 2024-01-19 04:21

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0099_auto_20240110_1048'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='paymenttype',
            name='format_string',
        ),
        migrations.AddField(
            model_name='paymenttype',
            name='format',
            field=models.CharField(default='number', max_length=100),
        ),
    ]