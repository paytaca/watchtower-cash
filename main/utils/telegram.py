from .subscription import save_subscription, remove_subscription
from main.tasks import send_telegram_message
from main.models import Token, Subscription
from main.utils.telegram_responses import get_message
import logging
import re

logger = logging.getLogger(__name__)

class TelegramBotHandler(object):

    def __init__ (self, data={}):
        self.data = data
        self.message = ""
        self.text = ''
        self.subscribe_regex = f"(^subscribe\s+(simpleledger:.*|bitcoincash:.*))$"
        self.unsubscribe_regex = f"(^unsubscribe\s+(simpleledger:.*|bitcoincash:.*))$"        

    def verify_address(self, token_name, address):
        #verify address
        proceed = False
        if address.startswith('simpleledger:') and len(address) == 55:                                
            if token_name != 'bch':
                proceed = True
            else:                                     
                self.message+= '\nPlease enter your <b>BCH address</b> to watch <b>BCH</b>.\n\nExample:'
                self.message+= '\nsubscribe bitcoincash:qrry9hqfzhmkxlzf5m3f45y92l9gk5msgyustqp7vh bch'

        elif address.startswith('bitcoincash:') and len(address) == 54:                                
            if token_name == 'bch':
                proceed = True
            else:                                    
                self.message+= '\nPlease enter your <b>SLP address</b> to watch <b>SLP tokens</b>.\n\nExample:'
                self.message+= '\nsubscribe simpleledger:qpgje2ycwhh2rn8v0rg5r7d8lgw2pp84zgpkd6wyer spice'

        elif address.startswith('simpleledger:') and not len(address) == 55:                                
            self.message = "<b>You have entered an invalid SLP address!</b>  🚫"

        elif address.startswith('bitcoincash:') and not len(address) == 54:                                
            self.message = "<b>You have entered an invalid BCH address!</b>  🚫"
        return proceed

    def get_info(self):
        if len(self.text.split()) > 1:
            return self.text.split()[1].strip()
        else:
            return '' 

    def scan_request(self, action, chat_id):
        default_response = False
        address = self.get_info()
        if address:                                
            #save subcscription
            if action == 'subscribe':
                new_sub = save_subscription(address, chat_id)
                if new_sub:
                    self.message = "Your address has been successfully saved!"
                else:
                    self.message = "You already subscribed this address"
            elif action == 'unsubscribe':
                old_sub = remove_subscription(address, chat_id)
                if old_sub:
                    self.message = "Your address has been successfully removed!"
                else:
                    self.message = "Sorry, address can't be removed."

        elif self.message == '':
            self.message = "Invalid input, please try again."
        return default_response

    def handle_message(self):
        
        if self.data:

            #process message
            if 'message' in self.data.keys():
            
                #get user data
                chat_id=self.data['message']['chat']['id']
                update_id=self.data['update_id']
                username=self.data['message']['from']['username'] or self.data['message']['from']['first_name'] 
                self.text = self.data['message']['text']

                #check if private message
                if self.data['message']['chat']['type'] == 'private':
                    
                    default_response = True
                    self.text = self.text.replace('/', '')
                    #help message

                    if self.text.lower() == 'help':
                        self.message = get_message('help')
                        default_response = False
                    
                    #check subscription message
                    proceed = False
                    if re.findall(self.subscribe_regex, self.text.lower()):                            
                        default_response = self.scan_request('subscribe', chat_id)
                    
                    #check unsubscription message
                    elif re.findall(self.unsubscribe_regex, self.text.lower()):
                        default_response = self.scan_request('unsubscribe', chat_id)
                        
                    if default_response:
                        #Default Message
                        self.message = get_message('default')
                    send_telegram_message(self.message, chat_id)
