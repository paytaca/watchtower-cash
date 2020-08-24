from rest_framework.viewsets import ViewSet
from drf_yasg.utils import swagger_auto_schema
from main.serializers.serializer_account import CreateAccountSerializer

class Account(ViewSet):
    
    def create_account(self, request, *args, **kwargs):
        request_serializer = CreateAccountSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        data = request_serializer.data
        return Response(data=data, status=200)
