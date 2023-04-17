from django.core.exceptions import ValidationError
from django.db.models import Q
from .base_models import (
    Status, StatusType
)

def validate_status_confirmed(order_id):
    # check: current order status must be CONFIRMED
    current_status = Status.objects.filter(order=order_id).latest('created_at')
    if current_status.status != StatusType.CONFIRMED:
        raise ValidationError('ValidationError: action requires order\'s current status is CONFIRMED')
  
def validate_status_inst_count(status, order_id):
    status_count = Status.objects.filter(Q(order=order_id) & Q(status=status)).count()
    if status_count > 0:
        raise ValidationError('duplicate status')
    
def validate_exclusive_stats(status, order_id):
    if status == StatusType.RELEASED:
        stat_count = Status.objects.filter(Q(order=order_id) & Q(status=StatusType.REFUNDED)).count()
        if stat_count > 0:
            raise ValidationError('cannot release what is already refunded')
    
    if status == StatusType.REFUNDED:
        stat_count = Status.objects.filter(Q(order=order_id) & Q(status=StatusType.RELEASED)).count()
        if stat_count > 0:
            raise ValidationError('cannot refund what is already released')
        
def validate_status_progression(new_status, order_id):
    current_status = Status.objects.filter(Q(order=order_id)).latest('created_at')
    error_msg = 'ValidationError: '
    if (current_status.status == StatusType.RELEASED or 
        current_status.status == StatusType.REFUNDED or
        current_status.status == StatusType.CANCELED):
       raise ValidationError(error_msg + 'Cannot change a completed order\'s status')

    if current_status.status == StatusType.SUBMITTED:
        if (new_status != StatusType.CONFIRMED and
            new_status != StatusType.CANCELED):
            raise ValidationError(error_msg + 'SUBMITTED orders can only be CONFIRMED | CANCELED')

    if current_status.status == StatusType.CONFIRMED:
       if (new_status != StatusType.PAID_PENDING and 
           new_status != StatusType.CANCEL_APPEALED):
          raise ValidationError(error_msg + 'CONFIRMED orders can only be PAID_PENDING | CANCEL_APPEALED')
    
    if current_status.status == StatusType.PAID_PENDING:
       if (new_status != StatusType.PAID and 
           new_status != StatusType.REFUND_APPEALED):
          raise ValidationError(error_msg + 'PAID_PENDING orders can only be PAID | REFUND_APPEALED')
       
    if current_status.status == StatusType.PAID:
       if (new_status != StatusType.RELEASED and 
           new_status != StatusType.RELEASE_APPEALED):
          raise ValidationError(error_msg + 'PAID orders can only be RELEASED | RELEASE_APPEALED')
    
    if current_status.status == StatusType.CANCEL_APPEALED:
       if new_status != StatusType.REFUNDED:
          raise ValidationError(error_msg + 'CANCEL_APPEALED orders can only be REFUNDED')
    
    if (current_status.status == StatusType.RELEASE_APPEALED or 
        current_status.status == StatusType.REFUND_APPEALED):
       if (new_status != StatusType.RELEASED and 
           new_status != StatusType.REFUNDED):
          raise ValidationError(error_msg + 'RELEASE_APPEALED | REFUND_APPEALED orders can only be RELEASED | REFUNDED')
