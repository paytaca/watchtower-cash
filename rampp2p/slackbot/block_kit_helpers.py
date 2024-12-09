from rampp2p.models import StatusType

import logging
logger = logging.getLogger(__name__)

def format_timestamp(datetime_obj, format_text="{date_short_pretty} {time}"):

    timestamp = int(datetime_obj.timestamp())
    return f"<!date^{timestamp}^{format_text}|{datetime_obj}>"

def resolve_color_from_order_status(status):
    if status == StatusType.SUBMITTED:
        return "#2196f3"
    elif (status == StatusType.CONFIRMED or 
          status == StatusType.ESCROW_PENDING or 
          status == StatusType.ESCROWED or
          status == StatusType.PAID_PENDING or
          status == StatusType.PAID or 
          status == StatusType.APPEALED or
          status == StatusType.RELEASE_PENDING or
          status == StatusType.REFUND_PENDING):
        return '#ffa000'
    elif (status == StatusType.RELEASED or 
          status == StatusType.REFUNDED):
        return '#388e3c'
    elif status == StatusType.CANCELED:
        return '#f44336'
    else:
        return "#9e9e9e"
    
def resolve_color_from_appeal_status(appeal):
    if appeal.resolved_at:
        return '#388e3c'
    return '#ffa000'