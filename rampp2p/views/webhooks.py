from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from rampp2p.models import Order, Peer, Appeal
from django.http import Http404
from rampp2p.utils.notifications import send_push_notification

import logging
logger = logging.getLogger(__name__)

class ChatWebhookView(APIView):
    def get_object(self, chat_session_ref):
        try:
            return Order.objects.get(chat_session_ref=chat_session_ref)
        except Order.DoesNotExist:
            raise Http404
        
    def post(self, request):
        # send push notifications
        chat_identity = request.data.get('chat_identity')
        order = self.get_object(request.data.get('chat_session_ref'))

        sender = Peer.objects.filter(chat_identity_id=chat_identity.get('id'))
        if sender.exists():
            sender = sender.first()
        else:
            logger.warn(f'Unable to find Peer with chat_identity_id {chat_identity.id}.')
        
        counterparty = None
        if sender.wallet_hash == order.ad_snapshot.ad.owner.wallet_hash:
            counterparty = order.owner.wallet_hash
        else:
            counterparty = order.ad_snapshot.ad.owner.wallet_hash
        recipients = [counterparty]

        extra_data = {
            'type': 'new_message',
            'order_id': order.id
        }

        appeal = Appeal.objects.filter(order=order)
        if appeal.exists() and order.arbiter:
            appeal = appeal.first()
            extra_data['appeal_id'] = appeal.id
            message = f'New message from Appeal No. {appeal.id}'
            send_push_notification([order.arbiter.wallet_hash], message, extra=extra_data)
        
        message = f'New message from Order No. {order.id}'
        send_push_notification(recipients, message, extra=extra_data)
        return Response(status=status.HTTP_200_OK)
