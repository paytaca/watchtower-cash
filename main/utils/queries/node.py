from main.utils.queries.bchn import *
from main.utils.queries.bitcoin_verde import *


class Node(object):

    def __init__(self):
        self.BCH = BCHN()  # cashtokens too
        self.SLP = BitcoinVerde()
    
