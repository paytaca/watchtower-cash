# Generated by Django 3.0.14 on 2024-09-06 07:50

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('paytacapos', '0029_auto_20240905_0617'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='merchant',
            name='verification_category',
        ),
    ]
