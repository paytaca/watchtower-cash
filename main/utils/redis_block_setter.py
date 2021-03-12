from django.conf import settings
import json
from main.models import BlockHeight
from main.utils import missing_blocks
redis_storage = settings.REDISKV

def block_setter(number, new=False):
    added = False
    if b'PENDING-BLOCKS' not in redis_storage.keys('*'):
        data = json.dumps([])
        redis_storage.set('PENDING-BLOCKS', data)
    blocks = json.loads(redis_storage.get('PENDING-BLOCKS'))
    active_block = redis_storage.get('ACTIVE-BLOCK')
    if number not in blocks and f"\b{number}" != active_block:
        if new or len(blocks) == 0:
            blocks.append(number)
            added = True
    allblocks = list(BlockHeight.objects.values_list('number', flat=True))
    neglected_blocks = list(missing_blocks(allblocks,0,len(allblocks)-1))
    for number in neglected_blocks:
        BlockHeight.objects.get_or_create(number=number)
        blocks.append(number)
    blocks = list(set(blocks))
    blocks.sort()
    data = json.dumps(blocks)
    redis_storage.set('PENDING-BLOCKS', data)
    return added, len(neglected_blocks)


    