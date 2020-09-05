from django.http import JsonResponse
from django.conf import settings
from django.views import View

from main.utils.slack import SlackBotHandler
from main.utils.slack_responses import get_message
from main.tasks import send_slack_message
from main.models import Token

import logging
import json


LOGGER = logging.getLogger(__name__)


class SlackDirectMessageView(View):

    def post(self, request):
        data = json.loads(request.body)
        request_type = data.get('type', '')
        response = {"OK": "POST request processed"}
        
        # check if Slack request is from our bot via verification token or signing secret
        token = data.get('token', '')
        if token != settings.SLACK_VERIFICATION_TOKEN and token != settings.SLACK_SIGNING_SECRET:
            return Response(status=403)

        # check if request is for URL verification when first verifying the request URL in Slack App Site
        # otherwise go to Slack bot message handler
        if request_type == 'url_verification':
            response = {
                "challenge": data.get('challenge', '')
            }
        else:
            slackbothandler = SlackBotHandler()
            slackbothandler.handle_message(data)

        return JsonResponse(response)


class SlackNotificationView(View):

    def post(self, request):
        response = {'success': False}

        # payload from client_acknowledgement in tasks.py
        amount = request.POST.get('amount', None)
        address = request.POST.get('address', None)
        source = request.POST.get('source', None)
        token = request.POST.get('token', None)
        txid = request.POST.get('txid', None)
        block = request.POST.get('block', None)
        spent_index = request.POST.get('spent_index', 0)
        channel_id_list = request.POST.get('channel_id_list', None)

        if amount and address and source and token and txid:
            amount = round(amount, 8)
            amount = format(amount, ',')

            if address.startswith('bitcoincash'):
                token = 'BCH'
            else:
                token = Token.objects.get(tokenid=token).name.upper()

            for channel_id_obj in channel_id_list:
                c_id = channel_id_obj['slack_user_details__channel_id']
                
                message = get_message('notification')
                attachment = [
                    {
                        "title": "SLP Notify Notification  :information_source:",
                        "text": (
                            f'• _*Address*_ = `{address}`'
                            + f'\n• _*Token*_ = `{token}`'
                            + f'\n• _*Amount*_ = `{amount}`' 
                            + f'\n• _*TXID*_ = `{txid}`'
                        ),
                        "color": settings.SLACK_THEME_COLOR
                    }
                ]
                send_slack_message.delay(message, c_id, attachment)

            response['success'] = True
            

        return JsonResponse(response)
    
