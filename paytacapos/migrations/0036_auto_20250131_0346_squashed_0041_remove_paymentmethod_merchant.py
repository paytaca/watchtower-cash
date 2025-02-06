# Generated by Django 3.0.14 on 2025-02-06 02:38

from django.db import migrations, models
import django.db.models.deletion

import logging
logger = logging.getLogger(__name__)

def init_payment_method_wallet(apps, schema_editor):
    # Initialize payment methods with null wallet field
    PaymentMethod = apps.get_model('paytacapos', 'PaymentMethod')
    Wallet = apps.get_model('main', 'Wallet')

    payment_methods = PaymentMethod.objects.filter(wallet__isnull=True)
    logger.warning(f'Initializing {payment_methods.count()} payment_methods')
    
    for payment_method in payment_methods:
        wallet = Wallet.objects.filter(wallet_hash=payment_method.merchant.wallet_hash)
        if not wallet.exists():
            continue

        payment_method.wallet = wallet.first()
        payment_method.save()

class Migration(migrations.Migration):

    replaces = [('paytacapos', '0036_auto_20250131_0346'), ('paytacapos', '0037_auto_20250131_0837'), ('paytacapos', '0038_cashoutorder_payment_method'), ('paytacapos', '0039_auto_20250206_0153'), ('paytacapos', '0040_init_payment_method_wallet_20250206_0154'), ('paytacapos', '0041_remove_paymentmethod_merchant')]

    dependencies = [
        ('paytacapos', '0035_merge_20250127_0141'),
        ('rampp2p', '0230_auto_20250120_0301'),
        ('main', '0099_cashnonfungibletoken_fixed_supply'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cashouttransaction',
            name='transaction',
            field=models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, to='main.Transaction'),
        ),
        migrations.AlterField(
            model_name='cashouttransaction',
            name='wallet_history',
            field=models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, to='main.WalletHistory'),
        ),
        migrations.AlterUniqueTogether(
            name='paymentmethod',
            unique_together={('payment_type', 'merchant')},
        ),
        migrations.AddField(
            model_name='cashoutorder',
            name='payment_method',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='paytacapos.PaymentMethod'),
        ),
        migrations.AddField(
            model_name='paymentmethod',
            name='wallet',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='main.Wallet'),
        ),
        migrations.AlterUniqueTogether(
            name='paymentmethod',
            unique_together={('payment_type', 'wallet')},
        ),
        migrations.RunPython(
            code=init_payment_method_wallet,
        ),
        migrations.RemoveField(
            model_name='paymentmethod',
            name='merchant',
        ),
    ]
