# Generated by Django 3.0.14 on 2024-03-18 03:57

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0122_auto_20240314_1552'),
    ]

    operations = [
        migrations.AlterField(
            model_name='paymenttype',
            name='format',
            field=models.CharField(choices=[('MOBILE NUMBER', 'Mobile Number'), ('EMAIL', 'Email'), ('ALPHANUMERIC STRING', 'Default')], db_index=True, default='ALPHANUMERIC STRING', max_length=64),
        ),
    ]
