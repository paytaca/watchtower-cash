from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import Http404
from django.core.exceptions import ValidationError
from ..models.peer import Peer
from ..serializers.peer import PeerSerializer
from ..utils import verify_signature

class PeerList(APIView):

  # list peers
  def get(self, request):
    queryset = Peer.objects.all()
    
    is_arbiter = request.query_params.get('is_arbiter', None)
    if is_arbiter is not None:
      queryset = queryset.filter(is_arbiter=is_arbiter)

    serializer = PeerSerializer(queryset, many=True)
    return Response(serializer.data, status.HTTP_200_OK)

  # create peer
  def post(self, request):

    # TODO: verify the signature
    # try:
    #   verify_signature(request)
    # except ValidationError as err:
    #   return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
    
    # create new Peer instance
    serializer = PeerSerializer(data=request.data)
    if serializer.is_valid():
      serializer.save()
      return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class PeerDetail(APIView):
  # get object
  def get_object(self, pk):
    try:
      return Peer.objects.get(pk=pk)
    except Peer.DoesNotExist:
      raise Http404

  # get peer
  def get(self, request, pk):
    peer = self.get_object(pk)
    serializer = PeerSerializer(peer)
    return Response(serializer.data, status=status.HTTP_200_OK)

  # update peer
  def put(self, request, pk):

    # TODO: verify the signature
    # try:
    #   verify_signature(request)
    # except ValidationError as err:
    #   return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)

    peer = self.get_object(pk)
    serializer = PeerSerializer(peer, data=request.data)
    if serializer.is_valid():
      serializer.save()
      return Response(serializer.data, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)