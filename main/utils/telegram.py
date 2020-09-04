from main.tasks import send_telegram_message
from main.models import Token, Subscription, Subscriber
from main.utils.responses import get_message
import logging

logger = logging.getLogger(__name__)
#commands
	# help/start/etc
	#subscribe address

class TelegramBotHandler(object):

	def __init__ (self, data={}):
		self.data = data
		self.message = ""
		self.text = ''
		self.subscribe_markup = {
            "inline_keyboard": [
                [
                    {'text': 'Subscribe', 'callback_data': 'subscribe'}              
                ]
            ]
        }
		self.token_names = self.token_list()

	# def generate_token_markup(self):
	# 	tokens = Token.objects.all()
	# 	inline_keyboard = []
		
	# 	for token in tokens:
	# 		temp = [{'text': token.name.upper(), 'callback_data': token.name}]

	# 		inline_keyboard.append(temp)
		
	# 	markup = {
	# 		"inline_keyboard": inline_keyboard
	# 	}

	# 	return markup

	def token_list(self):
		tokens = Token.objects.all()

		return [token.name for token in tokens]

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

				if self.text.replace('/', '').lower() == 'start': 
					#Default Message
					self.message = get_message('telegram_default')
					send_telegram_message(self.message, chat_id, update_id)

				if self.text.replace('/', '').lower() == 'help':
					self.message = get_message('telegram_help')
					send_telegram_message(self.message, chat_id, update_id)
