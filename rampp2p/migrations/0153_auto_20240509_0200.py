# Generated by Django 3.0.14 on 2024-05-09 02:00

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0152_auto_20240508_0628'),
    ]

    operations = [
        migrations.AlterField(
            model_name='paymenttype',
            name='short_name',
            field=models.CharField(default='', max_length=50),
        ),
    ]
