# Generated by Django 3.0.14 on 2023-10-17 04:21

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0089_auto_20231016_0709'),
    ]

    operations = [
        migrations.RenameField(
            model_name='peer',
            old_name='nickname',
            new_name='name',
        ),
    ]
