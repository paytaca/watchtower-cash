# Generated by Django 3.0.14 on 2021-07-03 06:56

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0032_auto_20210703_0205'),
    ]

    operations = [
        migrations.AddField(
            model_name='token',
            name='logo_url',
            field=models.URLField(blank=True),
        ),
    ]
