# Generated by Django 3.0.14 on 2023-05-02 07:10

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0029_order_fiat_amount'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='order',
            name='fiat_amount',
        ),
    ]
