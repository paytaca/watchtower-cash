# Generated by Django 3.0.14 on 2024-01-10 08:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0096_auto_20240104_0959'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='transaction',
            name='verifying',
        ),
        migrations.AlterField(
            model_name='arbiter',
            name='chat_identity_id',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='peer',
            name='chat_identity_id',
            field=models.IntegerField(blank=True, null=True),
        ),
    ]