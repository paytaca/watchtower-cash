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

        # NOTE: fetched second highest number (since first is a mysterious block w/ number that matches max int value)
        block = BlockHeight.objects.order_by('-number').filter(
            number__lt=1000000000
        ).first()

        serializer = self.get_serializer(data={'number': block.number})

        if serializer.is_valid():
            return Response(serializer.data, status=status.HTTP_200_OK)            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
