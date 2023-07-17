# Generated by Django 3.0.14 on 2023-05-02 07:49

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0030_remove_order_fiat_amount'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='arbiter_address',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AlterField(
            model_name='order',
            name='buyer_address',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AlterField(
            model_name='order',
            name='contract_address',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AlterField(
            model_name='order',
            name='seller_address',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]