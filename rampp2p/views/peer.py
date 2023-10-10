from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import Http404
from django.core.exceptions import ValidationError

from rampp2p.models import Peer
from rampp2p.serializers import (
    PeerSerializer, 
    PeerCreateSerializer,
    PeerUpdateSerializer
)
from rampp2p.viewcodes import ViewCode
from rampp2p.utils.signature import verify_signature, get_verification_headers

from rest_framework.decorators import authentication_classes
from authentication.token import TokenAuthentication

class PeerView(APIView):
    @authentication_classes([TokenAuthentication])
    def get(self, request):
        queryset = Peer.objects.all()
        
        id = request.query_params.get('id')
        if id is not None:
            queryset = queryset.filter(id=id)

        wallet_hash = request.headers.get('wallet_hash')
        if wallet_hash is not None:
            queryset = queryset.filter(wallet_hash=wallet_hash)

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
        
        serializer = PeerCreateSerializer(data=data)
        if serializer.is_valid():
            serializer = PeerSerializer(serializer.save())
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @authentication_classes([TokenAuthentication])
    def put(self, request):
        # TODO: allow users to update their public key and address, but this needs checking:
        # public key must match address
        
        serializer = PeerUpdateSerializer(request.user, data=request.data)
        if serializer.is_valid():
            serializer = PeerSerializer(serializer.save())
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)