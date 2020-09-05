from django.conf import settings

from main.models import (
    Subscriber,
    Subscription,
    Token
)
from main.utils.slack_responses import (
    get_message,
    get_attachment
)
from main.tasks import (
    send_slack_message,
    save_subscription,
    register_user
)

import requests, logging
import random, re
import json


LOGGER = logging.getLogger(__name__)


class SlackBotHandler(object):

    def __init__(self):
        self.simpleledger = 'simpleledger'
        self.bitcoincash = 'bitcoincash'
        slp_chars = ".{42}"
        bch_chars = ".{43}"
        self.token_regex = self.get_token_regex()
        self.subscribe_regex = f'^(subscribe\s(({self.simpleledger}:{slp_chars}\s{self.token_regex})|({self.bitcoincash}:{bch_chars})))$'

    
    def handle_message(self, data):
        self.data = data
        LOGGER.error(f"\n\nDATA: {data}\n\n")

        if 'event' in self.data.keys():
            event_dict = self.data['event']
            event_type = event_dict['type']

            if (event_type == 'message') and ('bot_id' not in event_dict.keys()) and ('text' in event_dict.keys()):
                text = self.clean_text(event_dict['text'])
                user_id = event_dict['user']
                channel = event_dict['channel']
                attachment = None
                message = ''

                if not self.user_is_registered(user_id):
                    slack_user_details = {
                        "id": user_id,
                        "channel_id": channel
                    }
                    register_user(slack_user_details, 'slack')


                if (text == 'subscribe' or text == 'tokens'):
                    message = get_message(text)
                    attachment = get_attachment(text)

                elif text.startswith('subscribe '):
                    if re.findall(self.subscribe_regex, text):
                        splitted_text = text.split()
                        address = splitted_text[1]
                        token = 'bch'

                        if address.startswith(self.simpleledger):
                            token = splitted_text[2].lower()

                        token_id = Token.objects.get(name__iexact=token).id
                        created = save_subscription(address, token_id, user_id, 'slack')

                        if created:
                            message = f'Your address `{address}` is now subscribed to SLP Notify Slack!  :tada:'
                            message += f'\nYou will now receive notifications for _{token.upper()}_ transactions made on that address.'
                        else:
                            message = f'Your address `{address}` is already subscribed with _{token}_ token!  :information_source:'
                    else:
                        message = get_message('subscribe')
                        attachment = get_attachment('subscribe')
                else:
                    message = get_message('default')
                    attachment = get_attachment('default')

                send_slack_message.delay(message, channel, attachment)


######### VALIDATION FUNCTIONS ##########

    def valid_address(self, address):
        if address.startswith(self.simpleledger) and len(address) == 55:
            return True
        elif address.startswith(self.bitcoincash) and len(address) == 54:
            return True
        return False


    # checks if a Slack user has connected its account to SLP Notify
    def user_is_registered(self, user_id):
        subscriber = Subscriber.objects.filter(slack_user_details__id=user_id)
        return subscriber.exists()
        

######### PROCESSING FUNCTIONS ###########

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
