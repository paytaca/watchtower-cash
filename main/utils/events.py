import logging
from main.models import Subscription

logger = logging.getLogger(__name__)

class EventHandler(object):

    def __init__(self):
        pass

    def watch(self, address):
        if address is not None:
            # Check subscription
            pass