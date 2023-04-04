from rest_framework import generics
from rest_framework.views import APIView
from ..models.peer import Peer
from ..serializers.peer import PeerSerializer

class PeerListCreate(generics.ListCreateAPIView):
  queryset = Peer.objects.all()
  serializer_class = PeerSerializer

class PeerDetail(generics.RetrieveUpdateAPIView):
  queryset = Peer.objects.all()
  serializer_class = PeerSerializer