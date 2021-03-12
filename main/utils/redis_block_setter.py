from django.conf import settings
import json
from main.models import BlockHeight
redis_storage = settings.REDISKV


def missing_blocks(L, start, end): 
    if end - start <= 1:  
        if L[end] - L[start] > 1: 
            yield from range(L[start] + 1, L[end]) 
        return   
    index = start + (end - start) // 2   
    # is the lower half consecutive? 
    consecutive_low =  L[index] == L[start] + (index - start) 
    if not consecutive_low: 
        yield from missing_blocks(L, start, index)   
    # is the upper part consecutive? 
    consecutive_high =  L[index] == L[end] - (end - index) 
    if not consecutive_high: 
        yield from missing_blocks(L, index, end)


def block_setter(number, new=False):
    if b'PENDING-BLOCKS' not in redis_storage.keys('*'): redis_storage.set('PENDING-BLOCKS', json.dumps([]))
    if b'ACTIVE-BLOCK' not in redis_storage.keys('*'): redis_storage.set('ACTIVE-BLOCK', '')
    added = False
    neglected_blocks = []

    blocks = json.loads(redis_storage.get('PENDING-BLOCKS'))
    active_block = redis_storage.get('ACTIVE-BLOCK')

    if number not in blocks and f"\b{number}" != active_block:
        if new or len(blocks) == 0:
            blocks.append(number)
            added = True
    
        allblocks = BlockHeight.objects.all()
        if allblocks.count():
            _all = list(allblocks.values_list('number', flat=True))
            neglected_blocks = list(missing_blocks(_all,0,len(_all)-1))
            for number in neglected_blocks:
                BlockHeight.objects.get_or_create(number=number)
                blocks.append(number)
    _blocks = list(set(blocks))
    _blocks.sort()
    _data = json.dumps(_blocks)
    redis_storage.set('PENDING-BLOCKS', _data)
    return added, len(neglected_blocks)


    