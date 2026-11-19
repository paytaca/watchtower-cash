from django.db import transaction
from django.http import Http404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from rampp2p.chat_webhook import MAX_EVENT_AGE, MAX_FUTURE_SKEW, verify_chat_webhook
from rampp2p.models import Order, Appeal, ChatWebhookDelivery
from rampp2p.utils.notifications import send_push_notification


class ChatWebhookIdentitySerializer(serializers.Serializer):
    id = serializers.IntegerField(min_value=1, max_value=2**63 - 1)


class ChatWebhookEventSerializer(serializers.Serializer):
    id = serializers.IntegerField(min_value=1, max_value=2**63 - 1)
    chat_session_ref = serializers.CharField(max_length=100)
    created_at = serializers.DateTimeField()
    chat_identity = ChatWebhookIdentitySerializer()


class ChatWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get_object(self, chat_session_ref):
        try:
            return Order.objects.select_related('owner', 'ad_snapshot__ad__owner', 'arbiter').get(chat_session_ref=chat_session_ref)
        except Order.DoesNotExist:
            raise Http404
        except Order.MultipleObjectsReturned:
            raise ValidationError('Ambiguous chat session reference.')

    def post(self, request):
        verify_chat_webhook(request)
        if request.headers.get('X-Chat-Webhook-Event') != 'new-message':
            raise ValidationError('Unsupported chat webhook event.')
        serializer = ChatWebhookEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event = serializer.validated_data
        now = timezone.now()
        if event['created_at'] < now - MAX_EVENT_AGE or event['created_at'] > now + MAX_FUTURE_SKEW:
            raise PermissionDenied('Chat webhook message is stale or future-dated.')

        order = self.get_object(event['chat_session_ref'])
        appeal = Appeal.objects.filter(order=order).first()
        peers = {peer.pk: peer for peer in (order.owner, order.ad_snapshot.ad.owner)}
        identity_id = event['chat_identity']['id']
        senders = [peer for peer in peers.values() if peer.chat_identity_id == identity_id]
        if appeal is not None and order.arbiter and order.arbiter.chat_identity_id == identity_id:
            senders.append(order.arbiter)
        # Reject outsiders and ambiguous identity mappings before any push.
        if len(senders) != 1:
            raise PermissionDenied('Chat sender is not an unambiguous order participant.')
        sender = senders[0]
        recipients = [peer.wallet_hash for peer in peers.values() if peer is not sender]
        extra = {'type': 'new_message', 'order_id': order.pk}
        if appeal is not None:
            extra['appeal_id'] = appeal.pk

        with transaction.atomic():
            _, created = ChatWebhookDelivery.objects.get_or_create(
                message_id=event['id'], defaults={'expires_at': event['created_at'] + MAX_EVENT_AGE},
            )
            if not created:
                return Response(status=status.HTTP_200_OK)
            # Keep the replay claim and sends together: failed delivery rolls
            # back the claim so a sender retry can attempt delivery again.
            # External pushes cannot be rolled back; partial provider failures
            # may still cause duplicate notifications on a subsequent retry.
            if appeal is not None and order.arbiter and sender is not order.arbiter:
                send_push_notification(
                    [order.arbiter.wallet_hash], f'New message from Appeal No. {appeal.pk}', extra=extra,
                )
            if recipients:
                send_push_notification(recipients, f'New message from Order No. {order.pk}', extra=extra)
        return Response(status=status.HTTP_200_OK)
