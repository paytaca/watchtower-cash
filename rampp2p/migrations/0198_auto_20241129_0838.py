# Generated by Django 3.0.14 on 2024-11-29 08:38

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0197_add_app_min_required_versions_20241120_0153'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='is_cash_in',
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]