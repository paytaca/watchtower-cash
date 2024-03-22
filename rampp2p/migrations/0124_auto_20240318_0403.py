# Generated by Django 3.0.14 on 2024-03-18 04:03

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0123_auto_20240318_0357'),
    ]

    operations = [
        migrations.AlterField(
            model_name='paymenttype',
            name='format',
            field=models.CharField(choices=[('MOBILE NUMBER', 'Mobile Number'), ('EMAIL', 'Email'), ('STRING', 'Default')], db_index=True, default='STRING', max_length=64),
        ),
    ]