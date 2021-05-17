from django.conf import settings
from .subscription import (
    save_subscription,
    register_user,
    remove_subscription
)
from main.models import (
    Subscription,
    SLPToken
)
from main.utils.slack_responses import (
    get_message,
    get_attachment
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
        bch_chars = ".{42}"
        self.token_regex = self.get_token_regex()
        self.subscribe_regex = f'^(subscribe\s(({self.simpleledger}:{slp_chars}\s{self.token_regex})|({self.bitcoincash}:{bch_chars})))$'
        self.unsubscribe_regex = self.subscribe_regex.replace('subscribe', 'unsubscribe')

    
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


                if (text == 'subscribe' or text == 'tokens' or text == 'unsubscribe'):
                    message = get_message(text)
                    attachment = get_attachment(text)

                elif text.startswith('subscribe ') or text.startswith('unsubscribe '):
                    splitted_text = text.split()
                    command = splitted_text[0]
                    command_regex = self.subscribe_regex

                    if command == 'unsubscribe':
                        command_regex = self.unsubscribe_regex
                    
                    if re.findall(command_regex, text):
                        address = splitted_text[1]
                        token = 'bch'

                        if address.startswith(self.simpleledger):
                            token = splitted_text[2].lower()

                        token_id = SLPToken.objects.get(name__iexactSLP=token).id
                        token = token.upper()

                        if command == 'subscribe':
                            created = save_subscription(address, token_id, user_id, 'slack')

                            if created:
                                message = f'Your address `{address}` is now subscribed to SLP Notify Slack!  :tada:'
                                message += f'\nYou will now receive notifications for _{token}_ transactions made on that address.'
                            else:
                                message = f'Your address `{address}` is already subscribed with _{token}_ token!  :information_source:'

                        elif command == 'unsubscribe':
                            success = remove_subscription(address, token_id, user_id, 'slack')

                            if success:
                                message = f'_{token}_ token notifications for address `{address}` has been removed  :no_entry:'
                                message += f'\nYou will no longer receive notifications for _{token}_ transactions on that address.'
                            else:
                                message = f'No address `{address}` is currently subscribed to _{token}_  :information_source:'
                    else:
                        message = get_message(command)
                        attachment = get_attachment(command)

                else:
                    message = get_message('default')
                    attachment = get_attachment('default')

                # send_slack_message.delay(message, channel, attachment)


######### VALIDATION FUNCTIONS ##########

    def valid_address(self, address):
        if address.startswith(self.simpleledger) and len(address) == 55:
            return True
        elif address.startswith(self.bitcoincash) and len(address) == 54:
            return True
        return False


    # checks if a Slack user has connected its account to SLP Notify
    def user_is_registered(self, user_id):
        # subscriber = Subscriber.objects.filter(slack_user_details__id=user_id)
        # return subscriber.exists()
        return False
        

######### PROCESSING FUNCTIONS ###########

    def get_token_regex(self):
        regex = ''

        for token in SLPToken.objects.exclude(name__iexact='bch'):
            regex += f'{token.name.lower()}|'
        
        regex = regex[0 : len(regex) - 1]
        regex = f'({regex})'
        return regex

    
    def clean_text(self, text):
        text = text.lower().strip()
        text = ' '.join(text.split())
        return text
