from django.conf import settings
import json

def block_setter(number):
    redis_storage = settings.REDISKV
    if b'PENDING-BLOCKS' not in redis_storage.keys('*'):
        data = json.dumps([])
        redis_storage.set('PENDING-BLOCKS', data)
    blocks = json.loads(redis_storage.get('PENDING-BLOCKS'))
    blocks = blocks.append(number)
    blocks = list(set(blocks))
    data = json.dumps(blocks)
    redis_storage.set('PENDING-BLOCKS', data)