from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.core.exceptions import ValidationError
from ..models.peer import Peer
from ..serializers.peer import PeerSerializer
from ..utils import verify_signature

class PeerList(generics.ListAPIView):
  queryset = Peer.objects.all()
  serializer_class = PeerSerializer

class PeerCreate(APIView):
  def post(self, request):

    # verify the signature
    try:
      verify_signature(request)
    except ValidationError as err:
      return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
    
    # create new Peer instance
    serializer = PeerSerializer(data=request.data)
    if serializer.is_valid():
      serializer.save()
      return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class PeerDetail(generics.RetrieveUpdateAPIView):
  queryset = Peer.objects.all()
  serializer_class = PeerSerializer