from django.conf import settings
import json
from main.models import BlockHeight
redis_storage = settings.REDISKV



def block_setter(number):
    if b'PENDING-BLOCKS' not in redis_storage.keys('*'): redis_storage.set('PENDING-BLOCKS', json.dumps([]))
    if b'ACTIVE-BLOCK' not in redis_storage.keys('*'): redis_storage.set('ACTIVE-BLOCK', '')
    added = False
    blocks = json.loads(redis_storage.get('PENDING-BLOCKS'))
    active_block = redis_storage.get('ACTIVE-BLOCK')
    if active_block: blocks.append(int(active_block))

    if number not in blocks:
        blocks.append(number)
        added = True

    beg = BlockHeight.objects.first().number
    end = BlockHeight.objects.last().number
    
    _all = list(BlockHeight.objects.values_list('number', flat=True))
    for i in range(beg, end):
        if i not in _all:
            obj, created = BlockHeight.objects.get_or_create(number=i)
            if created: blocks.append(number)

    if active_block: blocks.remove(int(active_block))
    _blocks = list(set(blocks))
    _blocks.sort()
    _data = json.dumps(_blocks)
    redis_storage.set('PENDING-BLOCKS', _data)
    return added


    