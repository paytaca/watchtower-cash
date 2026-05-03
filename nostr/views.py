from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from bitcoincash_oauth_django.drf_views import IsBitcoinCashAuthenticated
from .serializers import PushRegisterSerializer, PushUnregisterSerializer


class PushRegisterView(APIView):
    permission_classes = [IsBitcoinCashAuthenticated]
    serializer_class = PushRegisterSerializer

    @swagger_auto_schema(
        request_body=PushRegisterSerializer,
        responses={201: PushRegisterSerializer},
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"status": "registered"}, status=status.HTTP_201_CREATED)


class PushUnregisterView(APIView):
    permission_classes = [IsBitcoinCashAuthenticated]
    serializer_class = PushUnregisterSerializer

    @swagger_auto_schema(
        request_body=PushUnregisterSerializer,
        responses={200: PushUnregisterSerializer},
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"status": "unregistered"}, status=status.HTTP_200_OK)
