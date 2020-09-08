from main.tasks import send_telegram_message, save_subscription, register_user, remove_subscription
from main.models import Token, Subscription, Subscriber
from main.utils.telegram_responses import get_message
import logging
import re

logger = logging.getLogger(__name__)

class TelegramBotHandler(object):

    def __init__ (self, data={}):
        self.data = data
        self.message = ""
        self.text = ''
        self.subscribe_regex = f"(^subscribe\s+(simpleledger:.*|bitcoincash:.*)\s+{self.generate_token_regex()})$"
        self.unsubscribe_regex = f"(^unsubscribe\s+(simpleledger:.*|bitcoincash:.*)\s+{self.generate_token_regex()})$"

    def generate_token_regex(self):
        tokens = Token.objects.all()
        token_names = [t.name.lower() for t in tokens]
        regex = f"({token_names[0]}"

        for token in token_names:
            if token != token_names[0]:
                regex += f"|{token}"

        return f"{regex})"    


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
        if len(self.text.split()) > 2:
            return self.text.split()[1].strip() , self.text.split()[-1].lower().strip()
        else:
            return '' , self.text.split()[-1].lower().strip()

    def scan_request(self, action, chat_id):
        default_response = False
        address, token_name = self.get_info()
        proceed = self.verify_address(token_name, address)

        #verify token
        token  = Token.objects.filter(name=token_name).first()

        if token and proceed:                                
            #save sucscription
            logger.error('saving subscription')
            if action == 'subscribe':
                new_sub = save_subscription(address, token.id, chat_id, 'telegram')
                if new_sub:
                    self.message = "Your address has been successfully saved!"
                else:
                    self.message = "You already subscribed this address"
            elif action == 'unsubscribe':
                old_sub = remove_subscription(address, token.id, chat_id, 'telegram')
                if old_sub:
                    self.message = "Your address has been successfully removed!"
                else:
                    self.message = "Sorry, address can't be removed."
        elif not token:                                
            self.message = "Sorry, the token you've input is not yet supported."
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
                    #check if account exists
                    subscriber = Subscriber.objects.filter(telegram_user_details__id=chat_id).first()

                    if subscriber and subscriber.confirmed:                    
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
                            address, token_name = self.get_info()
                            proceed = self.verify_address(token_name, address)
                            #verify token
                            token  = Token.objects.filter(name=token_name).first()
                        

                    elif subscriber and not subscriber.confirmed:
                            self.message = "<b>Account not yet confirmed</b>"

                    #not subscribed
                    else:
                        #Register user
                        register_user(self.data['message']['from'], 'telegram')
                        self.message = get_message('default')
                    

                    send_telegram_message(self.message, chat_id, update_id)



