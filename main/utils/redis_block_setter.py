from django.conf import settings
import json

def block_setter(number, new=False):
    added = False
    redis_storage = settings.REDISKV
    if b'PENDING-BLOCKS' not in redis_storage.keys('*'):
        data = json.dumps([])
        redis_storage.set('PENDING-BLOCKS', data)
    blocks = json.loads(redis_storage.get('PENDING-BLOCKS'))
    if number not in blocks:
        if new or len(blocks) < 3:
            blocks.append(number)
            added = True
    data = json.dumps(blocks)
    redis_storage.set('PENDING-BLOCKS', data)
    return added