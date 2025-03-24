from rest_framework.response import Response
from rest_framework import status

from main.utils.subscription import new_subscription
from rest_framework.permissions import AllowAny
from rest_framework import generics
from main import serializers

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
