from django.views import View
from django.http import JsonResponse
from main.utils.telegram import TelegramBotHandler

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

		return JsonResponse({"ok": "POST request processed"})