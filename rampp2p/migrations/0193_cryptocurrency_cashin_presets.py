# Generated by Django 3.0.14 on 2024-10-11 08:39

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0192_auto_20241007_1024'),
    ]

    operations = [
        migrations.AddField(
            model_name='cryptocurrency',
            name='cashin_presets',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]