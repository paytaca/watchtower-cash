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

class TelegramSendtoView(View):

    def post(self, request):
        response = {'success': False}
        chat_id_list = request.POST.get('chat_id_list', "[]")
        chat_id_list = json.loads(chat_id_list)

        for chat_id in chat_id_list:
            if chat_id:
                token = request.POST.get('token')
                token_name = Token.objects.filter(tokenid=token).first().name

                if not token_name:
                    token_name = 'bch'

                message=f"""<b>SLP Notify Notification</b> ℹ️

                \nYou've recieved <b>{request.POST.get('amount')} {token_name.upper()}</b> on <b>{request.POST.get('address')}</b>
                \nhttps://explorer.bitcoin.com/bch/tx/{request.POST.get('txid')}
                """

                send_telegram_message.delay(message, chat_id)
            response['success'] = True
        return JsonResponse(response)
