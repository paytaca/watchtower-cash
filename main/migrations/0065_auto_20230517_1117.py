# Generated by Django 3.0.14 on 2023-05-17 11:17

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0064_auto_20230404_0345'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='cashtokeninfo',
            name='date_created',
        ),
        migrations.RemoveField(
            model_name='cashtokeninfo',
            name='date_updated',
        ),
    ]
