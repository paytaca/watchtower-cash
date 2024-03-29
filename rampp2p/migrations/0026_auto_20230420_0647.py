# Generated by Django 3.0.14 on 2023-04-20 06:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0025_remove_order_is_appealed'),
    ]

    operations = [
        migrations.AddField(
            model_name='paymentmethod',
            name='deleted_at',
            field=models.DateTimeField(null=True),
        ),
        migrations.AddField(
            model_name='paymentmethod',
            name='is_deleted',
            field=models.BooleanField(default=False),
        ),
    ]
