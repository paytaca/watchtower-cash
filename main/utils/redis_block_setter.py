from django.conf import settings
import json
from main.models import BlockHeight

redis_storage = settings.REDISKV

def block_setter(number, new=False):
    added = False
    if b'PENDING-BLOCKS' not in redis_storage.keys('*'):
        data = json.dumps([])
        redis_storage.set('PENDING-BLOCKS', data)
    blocks = json.loads(redis_storage.get('PENDING-BLOCKS'))
    if new or len(blocks) == 0:
        latest_block_number = BlockHeight.objects.last().number
        diff = latest_block_number - number
        if diff < 100:
            blocks.append(number)
            added = True
    data = json.dumps(blocks)
    redis_storage.set('PENDING-BLOCKS', data)
    return added