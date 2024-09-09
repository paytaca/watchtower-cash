from django.core.exceptions import ValidationError
from django.db.models import Q
from rampp2p.models import Status, StatusType

def validate_status(order_id: int, status: StatusType):
    current_status = Status.objects.filter(order__id=order_id).latest('created_at')
    if current_status.status != status:
        raise ValidationError(f'action requires status={status}')

def validate_status_confirmed(order_id):
    current_status = Status.objects.filter(order=order_id).latest('created_at')
    if current_status.status != StatusType.ESCROWED:
        raise ValidationError(f'action requires status={StatusType.ESCROWED}')
  
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
    if (current_status.status == StatusType.RELEASED or 
        current_status.status == StatusType.REFUNDED):
            raise ValidationError('Cannot change a completed order\'s status')

    invalid_status = False
    error_message = f'Invalid Status: Cannot change order status from {current_status.status} to {new_status}'
    if current_status.status == StatusType.SUBMITTED:
        if (new_status != StatusType.CONFIRMED and
            new_status != StatusType.CANCELED):
            invalid_status = True
        
    if current_status.status == StatusType.CONFIRMED:
        if (new_status != StatusType.ESCROW_PENDING and
            new_status != StatusType.CANCELED):
                invalid_status = True

    if current_status.status == StatusType.ESCROW_PENDING:
        if (new_status != StatusType.ESCROWED):
                invalid_status = True
         
    if current_status.status == StatusType.ESCROWED:
        if (new_status != StatusType.PAID_PENDING and 
            new_status != StatusType.APPEALED):
                invalid_status = True
    
    if current_status.status == StatusType.PAID_PENDING:
        if (new_status != StatusType.PAID and 
            new_status != StatusType.APPEALED):
                invalid_status = True
       
    if current_status.status == StatusType.PAID:
        if (new_status != StatusType.RELEASED and 
            new_status != StatusType.APPEALED):
                invalid_status = True
    
    if (current_status.status == StatusType.APPEALED):
        was_marked_paid = Status.objects.filter(Q(order=order_id) & Q(status=StatusType.PAID)).count() > 0
        if was_marked_paid:
            if (new_status != StatusType.RELEASE_PENDING):
                invalid_status = True
                error_message = f'Cannot change order status from {current_status.status} to {new_status}. Order previously marked as {StatusType.PAID.label}.'
        else:
            if (new_status != StatusType.RELEASE_PENDING and 
                new_status != StatusType.REFUND_PENDING):
                    invalid_status = True
    
    if (current_status.status == StatusType.RELEASE_PENDING):
        if (new_status != StatusType.RELEASED):
            invalid_status = True
        
    if (current_status.status == StatusType.REFUND_PENDING):
        if (new_status != StatusType.REFUNDED):
            invalid_status = True

    if invalid_status:
        raise ValidationError(error_message)