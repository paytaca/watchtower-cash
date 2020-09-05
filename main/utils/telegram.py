from main.tasks import send_telegram_message, save_subscription, register_user
from main.models import Token, Subscription, Subscriber
from main.utils.telegram_responses import get_message
import logging
import re

logger = logging.getLogger(__name__)
#commands
	# help/start/etc
	#subscribe address

class TelegramBotHandler(object):

	def __init__ (self, data={}):
		self.data = data
		self.message = ""
		self.text = ''
		self.subscribe_regex = f"(^subscribe\s+(simpleledger:.*|bitcoincash:.*)\s+{self.generate_token_regex()})$"

	def generate_token_regex(self):
		tokens = Token.objects.all()
		token_names = [t.name.lower() for t in tokens]
		regex = f"({token_names[0]}"

		for token in token_names:
			if token != token_names[0]:
				regex += f"|{token}"

		return f"{regex})"	


	def handle_message(self):
		
		if self.data:
			logger.error('entered')

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
						#help message
						if self.text.replace('/', '').lower() == 'help':
							self.message = get_message('help')
							default_response = False


						#check subscription message
						proceed = False
						if re.findall(self.subscribe_regex, self.text):
							address = self.text.split()[1].strip()
							token_name = self.text.split()[-1].strip().lower()

							#verify address
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

							elif addr_temp.startswith('simpleledger') and not len(addr_temp) == 55:
								self.message = "<b>You have entered an invalid SLP address!</b>  🚫"

							elif addr_temp.startswith('bitcoincash') and not len(addr_temp) == 54:
								self.message = "<b>You have entered an invalid BCH address!</b>  🚫"

							#verify token
							token  = Token.objects.filter(name=token_name).first()

							if token and proceed:
								#save sucscription
								logger.error('saving subscription')
								save_subscription(address, token.tokenid, chat_id, 'telegram')
								self.message = "Your address has been successfully saved!"

							else:
								self.message = "Sorry, the token you've input is not yet supported."

							default_response = False

						if default_response:
							#Default Message
							self.message = get_message('default')
						

					elif subscriber and not subscriber.confirmed:
							self.message = "<b>Account not yet confirmed</b>"

					#not subscribed
					else:
						#Register user
						register_user(self.data['message']['from'], 'telegram')
						self.message = get_message('default')
					

					send_telegram_message(self.message, chat_id, update_id)



