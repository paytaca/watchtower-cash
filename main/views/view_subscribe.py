import hmac
from rest_framework.response import Response
from rest_framework import status

from main.utils.subscription import new_subscription
from main.models import Recipient
from rest_framework.permissions import AllowAny
from rest_framework import generics
from rest_framework.views import APIView
from main import serializers
from main.serializers.serializer_webhook import (
    RecipientWebhookSecretCreateSerializer,
    RecipientWebhookSecretRotateSerializer,
)

import logging
LOGGER = logging.getLogger(__name__)


class SubscribeViewSet(generics.GenericAPIView):
    serializer_class = serializers.SubscriberSerializer
    permission_classes = [AllowAny,]

    def get_serializer_class(self, *args, **kwargs):
        return serializers.SubscriberSerializer

    def post(self, request, format=None):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            response = new_subscription(**serializer.data)
            return Response(response, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class RecipientWebhookSecretView(APIView):
    """
    Manage a Recipient and its webhook secret.

    POST  — Pre-create a Recipient and lock in a webhook secret before subscribing
            any addresses. First-one-wins: returns 409 if a Recipient for this
            web_url already exists.

            TODO Future improvement: validate that the caller actually controls the
            web_url via challenge-response — watchtower sends a GET request with a
            random token to the web_url and only proceeds if the server echoes it
            back. This would eliminate the remaining race window where an attacker
            pre-creates a recipient for a URL they don't own before the legitimate
            subscriber does.

    PATCH — Rotate or clear an existing webhook secret. Requires the current secret
            as proof of ownership. Returns 403 if no secret is set (use POST to set
            the initial secret) or if current_webhook_secret is wrong.
    """
    permission_classes = [AllowAny,]

    def post(self, request):
        serializer = RecipientWebhookSecretCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        web_url = serializer.validated_data['web_url']
        webhook_secret = serializer.validated_data['webhook_secret']

        if Recipient.objects.filter(web_url=web_url).exists():
            return Response({'error': 'recipient_already_exists'}, status=status.HTTP_409_CONFLICT)

        Recipient.objects.create(web_url=web_url, webhook_secret=webhook_secret)
        return Response({'success': True}, status=status.HTTP_201_CREATED)

    def patch(self, request):
        serializer = RecipientWebhookSecretRotateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        web_url = data['web_url']
        current_secret = data['current_webhook_secret']
        new_secret = data['new_webhook_secret'] or None

        recipient = Recipient.objects.filter(web_url=web_url).first()
        if not recipient:
            return Response({'error': 'recipient_not_found'}, status=status.HTTP_404_NOT_FOUND)

        if not recipient.webhook_secret:
            return Response({'error': 'no_webhook_secret_set'}, status=status.HTTP_403_FORBIDDEN)

        if not hmac.compare_digest(current_secret, recipient.webhook_secret):
            return Response({'error': 'invalid_current_webhook_secret'}, status=status.HTTP_403_FORBIDDEN)

        recipient.webhook_secret = new_secret
        recipient.save(update_fields=['webhook_secret'])
        return Response({'success': True}, status=status.HTTP_200_OK)
