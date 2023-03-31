from main.utils.queries.bchn import *
from main.utils.queries.bchd import *


class Node(object):

    def __init__(self):
        self.BCH = BCHN()  # cashtokens too
        self.SLP = BCHDQuery()
    
