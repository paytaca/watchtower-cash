# Generated by Django 3.0.14 on 2023-03-16 08:31

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ramp', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shift',
            name='quote_id',
            field=models.CharField(max_length=50, unique=True),
        ),
        migrations.AlterField(
            model_name='shift',
            name='shift_id',
            field=models.CharField(max_length=50, unique=True),
        ),
    ]
