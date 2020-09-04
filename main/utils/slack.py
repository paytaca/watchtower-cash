from django.conf import settings
from django.contrib.auth.models import User

from main.models import (
    Subscriber, 
    Subscription,
    Token
)
from main.utils.slack_responses import (
    get_message,
    get_attachment
)
from main.tasks import send_slack_message

import requests, logging
import random, re
import json


LOGGER = logging.getLogger(__name__)


class SlackBotHandler(object):

    def __init__(self):
        slp_chars = ".{42}"
        bch_chars = ".{43}"
        self.token_regex = self.get_token_regex()
        self.subscribe_regex = f'^(subscribe\s((simpleledger:{slp_chars}\s{self.token_regex})|(bitcoincash:{bch_chars})))$'

    
    def handle_message(self, data):
        self.data = data
        # LOGGER.error(f"\n\nDATA: {data}\n\n")

        if 'event' in self.data.keys():
            event_dict = self.data['event']
            event_type = event_dict['type']

            if event_type == 'message' and 'bot_id' not in event_dict.keys():
                text = self.clean_text(event_dict['text'])
                user = event_dict['user']
                channel = event_dict['channel']
                attachment = None
                message = ''

                if (text == 'subscribe' or text == 'tokens'):
                    message = get_message(text)
                    attachment = get_attachment(text)

                elif text.startswith('subscribe '):
                    if re.findall(self.subscribe_regex, text):
                        splitted_text = text.split()
                        address = splitted_text[1]
                        token = splitted_text[2]
                        

                else:
                    message = get_message('default')
                    attachment = get_attachment('default')

                send_slack_message.delay(message, channel, attachment)

    
    def get_token_regex(self):
        regex = ''

        for token in Token.objects.exclude(name__iexact='bch'):
            regex += f'{token.name.lower()}|'
        
        regex = regex[0 : len(regex) - 1]
        regex = f'({regex})'
        return regex
                    
    
    def clean_text(self, text):
        text = text.lower().strip()
        text = ' '.join(text.split())
        return text


    def valid_address(self, address):
        if address.startswith('simpleledger') and len(address) == 55:
            return True
        elif address.startswith('bitcoincash') and len(address) == 54:
            return True
        return False
