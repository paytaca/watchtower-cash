from rampp2p.models import StatusType

import logging
logger = logging.getLogger(__name__)

def format_timestamp(datetime_obj, format_text="{date_short_pretty} {time}"):

    timestamp = int(datetime_obj.timestamp())
    return f"<!date^{timestamp}^{format_text}|{datetime_obj}>"
