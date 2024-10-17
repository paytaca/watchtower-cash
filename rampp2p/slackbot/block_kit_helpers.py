from rampp2p.models import StatusType

import logging
logger = logging.getLogger(__name__)

def resolve_color_from_appeal_status(status:str):
    if status == StatusType.APPEALED:
        return '#ffbf00'
    elif status == StatusType.REFUNDED:
        return '#6495ed'
    elif status == StatusType.RELEASED:
        return '#40e0d0'
    else:
        return "#9e9e9e"

def resolve_color_from_order_status(status:str):
    if status == StatusType.SUBMITTED:
        return "#ffbf00"
    elif status == StatusType.CONFIRMED:
        return "#ffbf00"
    elif status == StatusType.ESCROW_PENDING:
        return '#ffbf00'
    elif status == StatusType.ESCROWED:
        return '#6495ed'
    elif status == StatusType.PAID_PENDING:
        return '#6495ed'
    elif status == StatusType.PAID:
        return '#40e0d0'
    elif status == StatusType.REFUNDED:
        return '#e74c3c'
    elif status == StatusType.RELEASED:
        return '#28b463'
    elif status == StatusType.CANCELED:
        return '#e74c3c'
    else:
        return "#9e9e9e"


def format_timestamp(datetime_obj, format_text="{date_short_pretty} {time}"):

    timestamp = int(datetime_obj.timestamp())
    return f"<!date^{timestamp}^{format_text}|{datetime_obj}>"
