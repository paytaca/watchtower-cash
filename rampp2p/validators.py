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
    prefix = 'ValidationError: '
    if (current_status.status == StatusType.RELEASED or 
        current_status.status == StatusType.REFUNDED or
        current_status.status == StatusType.CANCELED):
            raise ValidationError( f'{prefix} Cannot change a completed order\'s status')

    if current_status.status == StatusType.SUBMITTED:
        if (new_status != StatusType.ESCROW_PENDING and
            new_status != StatusType.CANCELED):
                raise ValidationError(f'{prefix} {StatusType.SUBMITTED.label} orders can only be {StatusType.ESCROW_PENDING.label} | {StatusType.CANCELED.label}')

    if current_status.status == StatusType.ESCROW_PENDING:
        if (new_status != StatusType.ESCROWED and
            new_status != StatusType.CANCELED):
                raise ValidationError(f'{prefix} {StatusType.ESCROW_PENDING.label} orders can only be {StatusType.ESCROWED.label} | {StatusType.CANCELED.label}')
         
    if current_status.status == StatusType.ESCROWED:
        if (new_status != StatusType.PAID_PENDING and 
            new_status != StatusType.REFUND_APPEALED):
                raise ValidationError(f'{prefix} {StatusType.ESCROWED.label} orders can only be {StatusType.PAID_PENDING.label} | {StatusType.REFUND_APPEALED.label}')
    
    if current_status.status == StatusType.PAID_PENDING:
        if (new_status != StatusType.PAID and 
            new_status != StatusType.RELEASE_APPEALED and
            new_status != StatusType.REFUND_APPEALED):
                raise ValidationError(f'{prefix} {StatusType.PAID_PENDING.label} orders can only be {StatusType.PAID} | {StatusType.RELEASE_APPEALED} | {StatusType.REFUND_APPEALED}')
       
    if current_status.status == StatusType.PAID:
        if (new_status != StatusType.RELEASED and 
            new_status != StatusType.RELEASE_APPEALED):
                raise ValidationError(f'{prefix} {StatusType.PAID.label} orders can only be {StatusType.RELEASED.label} | {StatusType.RELEASE_APPEALED.label}')
    
    if (current_status.status == StatusType.REFUND_APPEALED):
        if (new_status != StatusType.RELEASE_PENDING and 
            new_status != StatusType.REFUND_PENDING):
                raise ValidationError(f'{prefix} {StatusType.REFUND_APPEALED.label} orders can only be {StatusType.RELEASE_PENDING.label} | {StatusType.REFUND_PENDING.label}')

    if (current_status.status == StatusType.RELEASE_APPEALED):
        was_marked_paid = Status.objects.filter(Q(order=order_id) & Q(status=StatusType.PAID)).count() > 0
        if was_marked_paid:
            if (new_status != StatusType.RELEASE_PENDING):
                raise ValidationError(f'{prefix} {StatusType.RELEASE_APPEALED.label} orders previously marked as {StatusType.PAID.label} can only be {StatusType.RELEASE_PENDING.label}')
        else:
            if (new_status != StatusType.RELEASE_PENDING and 
                new_status != StatusType.REFUND_PENDING):
                    raise ValidationError(f'{prefix} {StatusType.RELEASE_APPEALED.label} orders can only be {StatusType.RELEASE_PENDING.label} | {StatusType.REFUND_PENDING.label}')
    
    if (current_status.status == StatusType.RELEASE_PENDING):
        if (new_status != StatusType.RELEASED):
            raise ValidationError(f'{prefix} {StatusType.RELEASE_PENDING} orders can only be {StatusType.RELEASED.label}')
        
    if (current_status.status == StatusType.REFUND_PENDING):
        if (new_status != StatusType.REFUNDED):
            raise ValidationError(f'{prefix} {StatusType.REFUND_PENDING} orders can only be {StatusType.REFUNDED.label}')