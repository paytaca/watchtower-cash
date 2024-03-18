# Generated by Django 3.0.14 on 2024-03-18 04:04

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0124_auto_20240318_0403'),
    ]

    operations = [
        migrations.AlterField(
            model_name='paymenttype',
            name='format',
            field=models.CharField(choices=[('MOBILE NUMBER', 'Mobile Number'), ('EMAIL', 'Email'), ('STRING', 'String')], db_index=True, default='STRING', max_length=64),
        ),
    ]
