from rampp2p.validators import validate_status_inst_count, validate_status_progression
from rampp2p.serializers.status import StatusSerializer, StatusReadSerializer
from django.core.exceptions import ValidationError

import logging
logger = logging.getLogger(__name__)

def update_order_status(order_id, status, wallet_hash=None):
    validate_status_inst_count(status, order_id)
    validate_status_progression(status, order_id)

    data={
        'status': status,
        'order': order_id
    }
    
    if wallet_hash:
        data['created_by'] = wallet_hash

    logger.warning(f'update_order_status: {data}')
    serializer = StatusSerializer(data=data)
    
    if not serializer.is_valid():
        raise ValidationError('invalid status')
    
    status = StatusReadSerializer(serializer.save())
    
    return status