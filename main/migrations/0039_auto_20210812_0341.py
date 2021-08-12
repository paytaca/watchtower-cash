# Generated by Django 3.0.14 on 2021-08-12 03:41

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0038_auto_20210812_0131'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscription',
            name='date_created',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AddField(
            model_name='token',
            name='date_created',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AddField(
            model_name='token',
            name='date_updated',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
