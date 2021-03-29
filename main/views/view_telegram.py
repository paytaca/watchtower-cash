from django.views import View
from django.http import JsonResponse
from main.utils.telegram import TelegramBotHandler
from main.tasks import send_telegram_message
from main.models import Token
from rest_framework.views import APIView
from rest_framework import authentication, permissions
import logging
import json

logger = logging.getLogger(__name__)


class TelegramBotView(View):

    def post(self, request):
        data = json.loads(request.body)

        handler = TelegramBotHandler(data)
        handler.handle_message()

        return JsonResponse({"ok": "POST request processed"})
