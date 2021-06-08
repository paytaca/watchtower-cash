from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import generics
from rest_framework import status
from main import serializers
from main.tasks import broadcast_transaction

class BroadcastViewSet(generics.GenericAPIView):
    serializer_class = serializers.BroadcastSerializer
    permission_classes = [AllowAny,]

    def post(self, request, format=None):
        serializer = self.get_serializer(data=request.data)
        response = {'success': False}
        if serializer.is_valid():
            job = broadcast_transaction.delay(serializer.data['transaction'])
            success, result = job.get()
            if success:
                response['txid'] = result
                response['success'] = True
                return Response(response, status=status.HTTP_200_OK)
            else:
                response['error'] = result
                return Response(response, status=status.HTTP_409_CONFLICT)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
