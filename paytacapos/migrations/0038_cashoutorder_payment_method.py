# Generated by Django 3.0.14 on 2025-02-04 01:42

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('paytacapos', '0037_auto_20250131_0837'),
    ]

    operations = [
        migrations.AddField(
            model_name='cashoutorder',
            name='payment_method',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='paytacapos.PaymentMethod'),
        ),
    ]
