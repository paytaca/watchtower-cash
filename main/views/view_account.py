from rest_framework.viewsets import ViewSet
from drf_yasg.utils import swagger_auto_schema
from main.serializers.create_account_serializer import CreateAccountSerializer
class Account(ViewSet):
    
    
    @swagger_auto_schema(method="post", request_body=CreateAccountSerializer, responses={200: CreateAccountSerializer(many=True)})
    @action(detail=False, url_path="create", methods=["post"])
    def create_account(self, request), *args, **kwargs):
        request_serializer = CreateAccountSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        data = request_serializer.data
        return Response(data=data, status=200)
