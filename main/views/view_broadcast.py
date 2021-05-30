from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from main.utils.queries.bchd import BCHDQuery
from rest_framework import generics
from main import serializers
from rest_framework import status

class BroadcastViewSet(generics.GenericAPIView):
    serializer_class = serializers.BroadcastSerializer
    permission_classes = [AllowAny,]

    def post(self, request, format=None):
        serializer = self.get_serializer(data=request.data)
        response = {'success': False}
        if serializer.is_valid():
            obj = BCHDQuery()
            txid = obj.broadcast_transaction(**serializer.data)
            response['txid'] = txid
            response['success'] = True
            if response['success']:
                return Response(response, status=status.HTTP_200_OK)
            else:
                return Response(response, status=status.HTTP_409_CONFLICT)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
