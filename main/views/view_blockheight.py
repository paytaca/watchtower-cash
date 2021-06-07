from rest_framework.response import Response
from rest_framework import status


from rest_framework.permissions import AllowAny
from rest_framework import generics
from main import serializers
from main.models import BlockHeight
from main.tasks import get_latest_block



class BlockHeightViewSet(generics.GenericAPIView):
    serializer_class = serializers.BlockHeightSerializer
    permission_classes = [AllowAny,]

    def get(self, request, format=None):
        get_latest_block()
        block = BlockHeight.objects.order_by('-number').first()
        serializer = self.get_serializer(data={'number': block.number})
        if serializer.is_valid():
            return Response(serializer.data, status=status.HTTP_200_OK)            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)