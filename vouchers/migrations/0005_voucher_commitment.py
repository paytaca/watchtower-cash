# Generated by Django 3.0.14 on 2024-01-08 02:07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vouchers', '0004_auto_20230926_0826'),
    ]

    operations = [
        migrations.AddField(
            model_name='voucher',
            name='commitment',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
    ]
