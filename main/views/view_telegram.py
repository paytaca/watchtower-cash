from django.views import View
from django.http import JsonResponse
from main.utils.telegram import TelegramBotHandler
from main.tasks import send_telegram_message
from main.models import Token

import logging
import json

logger = logging.getLogger(__name__)


class TelegramBotView(View):

	def post(self, request):
		data = json.loads(request.body)

		handler = TelegramBotHandler(data)
		handler.handle_message()

		return JsonResponse({"ok": "POST request processed"})

class TelegramSendtoView(View):

	def post(self, request):
		data = json.loads(request.body)

		chat_id_list = data['chat_id_list']

		for chat_id_obj in chat_id_list:
			chat_id = chat_id_obj['telegram_user_details__id']

			token_name = Token.objects.filter(tokenid=data['token']).first().name

			if not token_name:
				token_name = 'bch'

			message=f"""<b>SLP Notify Notification</b> ℹ️

			\nYou've recieved <b>{data['amount']} {token_name.upper()}</b> on <b>{data['address']}</b>
			\nhttps://explorer.bitcoin.com/bch/tx/{data['txid']}
			"""

			send_telegram_message(message, chat_id)

		return JsonResponse({"ok": "POST request processed"})
