# Generated by Django 3.0.14 on 2022-03-30 04:19

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0050_auto_20220217_0758'),
    ]

    operations = [
        migrations.AlterField(
            model_name='transaction',
            name='spent',
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]
