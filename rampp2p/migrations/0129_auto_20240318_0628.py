# Generated by Django 3.0.14 on 2024-03-18 06:28

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0128_auto_20240318_0622'),
    ]

    operations = [
        migrations.AlterField(
            model_name='paymentmethod',
            name='owner',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='rampp2p.Peer'),
        ),
        migrations.AlterField(
            model_name='paymentmethod',
            name='payment_type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='rampp2p.PaymentType'),
        ),
    ]
