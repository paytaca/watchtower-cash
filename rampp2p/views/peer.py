from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import Http404
from django.core.exceptions import ValidationError

from rampp2p.models import Peer
from rampp2p.serializers import PeerSerializer, PeerWriteSerializer
from rampp2p.viewcodes import ViewCode
from rampp2p.utils.signature import verify_signature, get_verification_headers

class PeerListCreate(APIView):
    def get(self, request):
        queryset = Peer.objects.all()
        
        is_arbiter = request.query_params.get('is_arbiter', None)
        if is_arbiter is not None:
            queryset = queryset.filter(is_arbiter=is_arbiter)

        serializer = PeerSerializer(queryset, many=True)
        return Response(serializer.data, status.HTTP_200_OK)

    def post(self, request):

        try:
            signature, timestamp, wallet_hash = get_verification_headers(request)
            public_key = request.headers.get('public_key')
            
            message = ViewCode.PEER_CREATE.value + '::' + timestamp
            verify_signature(wallet_hash, signature, message, public_key=public_key)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
        
        # create new Peer instance
        data = request.data.copy()
        data['wallet_hash'] = wallet_hash
        data['public_key'] = public_key
        
        serializer = PeerWriteSerializer(data=data)
        if serializer.is_valid():
            serializer = PeerSerializer(serializer.save())
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class PeerDetail(APIView):
    def get_object(self, pk):
        try:
            return Peer.objects.get(pk=pk)
        except Peer.DoesNotExist:
            raise Http404

    def get(self, request, pk):
        peer = self.get_object(pk)
        serializer = PeerSerializer(peer)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk):
        try:
            pubkey, signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.PUT_PEER.value + '::' + timestamp
            verify_signature(wallet_hash, pubkey, signature, message)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
        
        try:
            caller = Peer.objects.get(wallet_hash=wallet_hash)
            peer = Peer.objects.get(pk=pk)

            if caller.wallet_hash != peer.wallet_hash:
                return Response({'error': 'unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        except Peer.DoesNotExist:
            return Response({'error': 'no such Peer with wallet_hash'}, status=status.HTTP_400_BAD_REQUEST)
        
        data = request.data.copy()
        data['wallet_hash'] = peer.wallet_hash
        data['is_arbiter'] = peer.is_arbiter

        serializer = PeerWriteSerializer(peer, data=data)
        if serializer.is_valid():
            serializer = PeerSerializer(serializer.save())
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)