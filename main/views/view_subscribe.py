from rest_framework.response import Response
from rest_framework import status

from main.utils.subscription import new_subscription
from rest_framework.permissions import AllowAny
from rest_framework import generics
from main import serializers



class SubscribeViewSet(generics.GenericAPIView):
    permission_classes = [AllowAny,]

    def post(self, request, format=None):
        data = None
        try:
            serializer = serializers.SubscriberSerializerPgpInfo(data=request.data)
            if serializer.is_valid():
                data = serializer.data
        except KeyError:
            serializer = serializers.SubscriberSerializer(data=request.data)
            if serializer.is_valid():
                data = serializer.data
        if data:
            response = new_subscription(**serializer.data)
            return Response(response, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
