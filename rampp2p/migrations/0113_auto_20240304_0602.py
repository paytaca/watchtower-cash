# Generated by Django 3.0.14 on 2024-03-04 06:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0112_auto_20240226_0501'),
    ]

    operations = [
        migrations.AddField(
            model_name='contract',
            name='address_type',
            field=models.CharField(max_length=10, null=True),
        ),
        migrations.AlterField(
            model_name='contract',
            name='version',
            field=models.CharField(max_length=100, null=True),
        ),
    ]
