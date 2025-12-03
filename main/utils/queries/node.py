from main.utils.queries.bchn import *
from main.utils.queries.bchd import *
from django.conf import settings


class Node(object):

    def __init__(self):
        self.BCH = BCHN()  # cashtokens too
        if not getattr(settings, 'DISABLE_BCHD', True):
            self.SLP = BCHDQuery()
        else:
            self.SLP = None
    
