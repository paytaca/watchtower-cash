# Generated by Django 3.0.14 on 2024-01-26 05:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0105_contractmember'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contractmember',
            name='member_type',
            field=models.CharField(choices=[('SELLER', 'Seller'), ('BUYER', 'Buyer'), ('ARBITER', 'Arbiter')], max_length=10),
        ),
    ]
