# Generated by Django 3.0.14 on 2022-03-30 01:06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('smartbch', '0002_transactiontransferreceipientlog'),
    ]

    operations = [
        migrations.AlterField(
            model_name='block',
            name='block_number',
            field=models.DecimalField(decimal_places=0, max_digits=78, unique=True),
        ),
        migrations.AlterField(
            model_name='tokencontract',
            name='address',
            field=models.CharField(max_length=64, unique=True),
        ),
        migrations.AlterField(
            model_name='transaction',
            name='txid',
            field=models.CharField(db_index=True, max_length=70, unique=True),
        ),
    ]
