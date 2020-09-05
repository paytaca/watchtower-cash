from django.http import JsonResponse
from django.conf import settings
from django.views import View

from main.utils.slack import SlackBotHandler

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

        return JsonResponse(response)
    
