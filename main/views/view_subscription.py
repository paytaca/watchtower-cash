
from main.serializers import SubscriptionSerializer


from django.contrib.auth import get_user_model,  logout
from django.core.exceptions import ImproperlyConfigured
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from main import serializers
from main.utils.user_subscription import subscribe_to_address


class SubscriptionViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, ]
    serializer_class = serializers.SubscriptionSerializer

    @action(methods=['POST', ], detail=False)
    def set_address(self, request):
        request.data['user_id'] = request.user.id
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        subscription = subscribe_to_address(**serializer.validated_data)
        return Response(data=subscription, status=status.HTTP_200_OK)