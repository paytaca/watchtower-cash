# Generated by Django 3.0.14 on 2025-03-18 08:25

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('paytacapos', '0058_auto_20250317_0224'),
    ]

    operations = [
        migrations.RenameField(
            model_name='payoutaddress',
            old_name='index',
            new_name='address_index',
        ),
    ]
