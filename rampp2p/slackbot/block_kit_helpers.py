from rampp2p.models import StatusType

import logging
logger = logging.getLogger(__name__)

def resolve_color_from_order_status(status:str):
    if status == StatusType.SUBMITTED:
        return "#ffc107"
    elif status == StatusType.CONFIRMED:
        return "#2196f3"
    elif status == StatusType.ESCROW_PENDING:
        return '#ffb300'
    elif status == StatusType.ESCROWED:
        return '#ffa000'
    elif status == StatusType.PAID_PENDING:
        return '#43a047'
    elif status == StatusType.PAID:
        return '#4caf50'
    elif status == StatusType.REFUNDED:
        return '#43a047'
    elif status == StatusType.RELEASED:
        return '#388e3c'
    elif status == StatusType.CANCELED:
        return '#f44336'
    else:
        return "#9e9e9e"


def format_timestamp(datetime_obj, format_text="{date_short_pretty} {time}"):

    timestamp = int(datetime_obj.timestamp())
    return f"<!date^{timestamp}^{format_text}|{datetime_obj}>"
