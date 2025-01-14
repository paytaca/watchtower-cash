# Generated by Django 3.0.14 on 2025-01-07 03:31

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0097_merge_20241203_0838'),
    ]

    operations = [
        migrations.CreateModel(
            name='AppControl',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(choices=[('CASH_IN', 'Cash In'), ('P2P_EXCHANGE', 'P2P Exchange'), ('MARKETPLACE', 'Marketplace'), ('WALLET_CONNECT', 'Wallet Connect'), ('GIFTS', 'Gifts'), ('COLLECTIBLES', 'Collectibles'), ('ANYHEDGE', 'Anyhedge'), ('MAP', 'Map'), ('MERCHANT_ADMIN', 'Merchant Admin')], max_length=100, unique=True)),
                ('is_enabled', models.BooleanField(default=False)),
            ],
        ),
    ]
