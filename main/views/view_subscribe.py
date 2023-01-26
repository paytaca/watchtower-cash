from rest_framework.response import Response
from rest_framework import status

from main.utils.subscription import new_subscription
from rest_framework.permissions import AllowAny
from rest_framework import generics
from main import serializers

import logging
LOGGER = logging.getLogger(__name__)


class SubscribeViewSet(generics.GenericAPIView):
    serializer_class = serializers.SubscriberSerializerChatIdentity
    permission_classes = [AllowAny,]

    def get_serializer_class(self, *args, **kwargs):
        if self.request.data:
            if self.request.data.get('chat_identity'):
                return serializers.SubscriberSerializerChatIdentity
            else:
                return serializers.SubscriberSerializer
        else:
            return serializers.SubscriberSerializerChatIdentity

    def post(self, request, format=None):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            response = new_subscription(**serializer.data)
            return Response(response, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
