# Generated by Django 3.0.14 on 2024-07-18 08:17

from django.db import migrations
from django.db.models import Q
import logging
logger = logging.getLogger(__name__)

# create fields for each payment method
def init_paymentmethod_fields(apps, schema_editor):
    PaymentMethod = apps.get_model('rampp2p', 'PaymentMethod')
    PaymentTypeField = apps.get_model('rampp2p', 'PaymentTypeField')
    PaymentMethodField = apps.get_model('rampp2p', 'PaymentMethodField')
    payment_methods = PaymentMethod.objects.all()
    for payment_method in payment_methods:
        logger.warn(f'Creating fields for payment method: {payment_method.id}')
        if payment_method.account_name:
            # find account name field_reference
            field_reference = PaymentTypeField.objects.get(Q(payment_type=payment_method.payment_type) & Q(fieldname="Account Name"))
            fielddata = {
                'payment_method': payment_method,
                'field_reference': field_reference,
                'value': payment_method.account_name
            }
            PaymentMethodField.objects.create(**fielddata)
        
        # find format name field_reference
        field_reference = PaymentTypeField.objects.get(Q(payment_type=payment_method.payment_type) & Q(fieldname=payment_method.identifier_format.format))
        fielddata = {
            'payment_method': payment_method,
            'field_reference': field_reference,
            'value': payment_method.account_identifier
        }
        PaymentMethodField.objects.create(**fielddata)


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0168_init_paymenttype_fields_20240718_0815'),
    ]

    operations = [
        migrations.RunPython(init_paymentmethod_fields)
    ]