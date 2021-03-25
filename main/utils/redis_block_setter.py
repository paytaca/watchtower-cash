from django.conf import settings
import json
from main.models import BlockHeight
redis_storage = settings.REDISKV



def block_setter(number):
    if b'PENDING-BLOCKS' not in redis_storage.keys('*'): redis_storage.set('PENDING-BLOCKS', json.dumps([]))
    
    added = False

    blocks = json.loads(redis_storage.get('PENDING-BLOCKS'))
    
    if number not in blocks:
        blocks.append(number)
        added = True

    _blocks = list(set(blocks))
    _blocks.sort()
    _data = json.dumps(_blocks)
    redis_storage.set('PENDING-BLOCKS', _data)
    return added
 