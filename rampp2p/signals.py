from django.db.models import signals
from django.dispatch import receiver
from django.db.models.signals import m2m_changed

from rampp2p.slackbot.send import *
from rampp2p import models

import logging
logger = logging.getLogger(__name__)

@receiver(signals.post_save, sender=models.Status)
def on_order_update(sender, instance:models.Status, created:bool, raw:bool, using:str, update_fields:set, **kwargs):
    if created:
        OrderSummaryMessage.send_safe(instance.order.id)
        OrderStatusUpdateMessage.send_safe(instance.order.id)

    if (instance.status == models.StatusType.APPEALED or
        instance.status == models.StatusType.REFUND_PENDING or
        instance.status == models.StatusType.RELEASE_PENDING or
        instance.status == models.StatusType.REFUNDED or
        instance.status == models.StatusType.RELEASED):
        appeal = models.Appeal.objects.filter(order__id=instance.order.id).first()
        if appeal:
            AppealStatusUpdateMessage.send_safe(appeal.id, status=instance)

@receiver(signals.post_save, sender=models.Appeal)
def on_appeal_update(sender, instance:models.Appeal, created:bool, raw:bool, using:str, update_fields:set, **kwargs):
    AppealSummaryMessage.send_safe(instance.id)

@receiver(signals.pre_save, sender=models.Ad)
def before_ad_update(sender, instance, **kwargs):
    if instance.pk:
        previous = models.Ad.objects.get(pk=instance.pk)
        instance._previous_state = previous

@receiver(signals.post_save, sender=models.Ad)
def on_ad_update(sender, instance:models.Ad, created:bool, raw:bool, using:str, update_fields:set, **kwargs):
    AdSummaryMessage.send_safe(instance.id)
    if not created:
        resolve_updated_ad_fields(instance)

@receiver(m2m_changed, sender=models.Ad.payment_methods.through)
def handle_ad_payments_changed(sender, instance, action, reverse, model, pk_set, **kwargs):
    if action in ['pre_clear', 'pre_remove', 'pre_add']:
        payment_methods = instance.payment_methods.all()
        payment_type_names = []
        for method in payment_methods:
            payment_type_names.append(method.payment_type.short_name)
        instance._previous_payment_types = payment_type_names

    elif action in ['post_add', 'post_remove', 'post_clear']: 
        if hasattr(instance, '_previous_payment_types'):
            previous_payment_types = instance._previous_payment_types
            payment_methods = instance.payment_methods.all()
            current_payment_types = []
            for e in payment_methods:
                current_payment_types.append(e.payment_type.short_name)

            if sorted(previous_payment_types) != sorted(current_payment_types):
                context = {
                    'old': previous_payment_types,
                    'new': current_payment_types
                }
                send_ad_update_message(instance.id, 'payment_types', context=context)

def resolve_updated_ad_fields(instance: models.Ad):
    updated_fields = {}
    if hasattr(instance, '_previous_state'):
        for field in instance._meta.get_fields():
            if not hasattr(field, 'attname'):
                continue
            field_name = field.attname
            old_value = getattr(instance._previous_state, field_name)
            new_value = getattr(instance, field_name)
            
            if old_value != new_value:
                if field_name != 'modified_at':
                    context = {
                        'old': old_value,
                        'new': new_value
                    }

                    if (field_name == 'trade_amount_sats' or
                        field_name == 'trade_floor_sats' or
                        field_name == 'trade_ceiling_sats'):
                        in_fiat_name = 'trade_limits_in_fiat'
                        if field_name == 'trade_amount_sats':
                            in_fiat_name = 'trade_amount_in_fiat'

                        old_trade_amount_in_fiat = getattr(instance._previous_state, in_fiat_name)
                        new_trade_amount_in_fiat = getattr(instance, in_fiat_name)

                        old_currency = 'BCH'
                        new_currency = 'BCH'
                        if old_trade_amount_in_fiat:
                            old_currency = getattr(instance._previous_state, 'fiat_currency').symbol
                        
                        if new_trade_amount_in_fiat:
                            new_currency = getattr(instance, 'fiat_currency').symbol
                        
                        context['currency'] = {
                            'old': old_currency,
                            'new': new_currency
                        }

                    updated_fields[field_name] = context
                    send_ad_update_message(instance.id, field_name, context=context)
        logger.warning(f'Updated Fields: {updated_fields}')

    return updated_fields
        
def send_ad_update_message(ad_id, field_name, context=None):
    update_type = None
    if field_name == 'fiat_currency':
        update_type = AdUpdateType.CURRENCY
    elif field_name == 'price_type':
        update_type = AdUpdateType.PRICE_TYPE
    elif field_name == 'fixed_price':
        update_type = AdUpdateType.FIXED_PRICE
    elif field_name == 'floating_price':
        update_type = AdUpdateType.FLOATING_PRICE
    elif field_name == 'trade_floor_sats':
        update_type = AdUpdateType.TRADE_FLOOR
    elif field_name == 'trade_ceiling_sats':
        update_type = AdUpdateType.TRADE_CEILING
    elif field_name == 'trade_amount_sats':
        update_type = AdUpdateType.TRADE_AMOUNT
    elif field_name == 'trade_amount_in_fiat':
        update_type = AdUpdateType.TRADE_AMOUNT_IN_FIAT
    elif field_name == 'trade_limits_in_fiat':
        update_type = AdUpdateType.TRADE_LIMITS_IN_FIAT
    elif field_name == 'appeal_cooldown_choice':
        update_type = AdUpdateType.APPEAL_COOLDOWN
    elif field_name == 'is_public':
        update_type = AdUpdateType.VISIBILITY
    elif field_name == 'payment_types':
        update_type = AdUpdateType.PAYMENT_TYPES
    elif field_name == 'deleted_at':
        update_type = AdUpdateType.DELETED_AT
    else:
        return
    
    AdSummaryMessage.send_safe(ad_id)
    AdUpdateMessage.send_safe(ad_id, update_type=update_type, context=context)