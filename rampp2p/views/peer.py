from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response

from authentication.token import TokenAuthentication

from rampp2p.models import Peer, Arbiter
from rampp2p.serializers import (
    PeerSerializer, 
    PeerCreateSerializer,
    PeerUpdateSerializer,
    PeerProfileSerializer,
    ArbiterProfileSerializer
)
from rampp2p.viewcodes import ViewCode
from rampp2p.utils.signature import verify_signature, get_verification_headers

class PeerCreateView(APIView):
    def post(self, request):
        signature, timestamp, wallet_hash = get_verification_headers(request)
        public_key = request.headers.get('public_key')
        
        message = ViewCode.PEER_CREATE.value + '::' + timestamp
        verify_signature(wallet_hash, signature, message, public_key=public_key)

        arbiter = Arbiter.objects.filter(wallet_hash=wallet_hash)
        if arbiter.exists():
            return Response({'error': 'Users cannot be both Peer and Arbiter'}, status=status.HTTP_400_BAD_REQUEST)

        # create new Peer instance
        data = request.data.copy()
        data['wallet_hash'] = wallet_hash
        data['public_key'] = public_key
        
        serializer = PeerCreateSerializer(data=data)
        if serializer.is_valid():
            serializer = PeerSerializer(serializer.save())
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class PeerDetailView(APIView):
    authentication_classes = [TokenAuthentication]
    
    def get(self, request):
        queryset = Peer.objects.all()
        
        id = request.query_params.get('id')
        if id is not None:
            queryset = queryset.filter(id=id)

        wallet_hash = request.headers.get('wallet_hash')
        if wallet_hash is not None:
            queryset = queryset.filter(wallet_hash=wallet_hash)
        queryset = queryset.first()

        serializer = PeerSerializer(queryset)
        return Response(serializer.data, status.HTTP_200_OK)

    def put(self, request):        
        serializer = PeerUpdateSerializer(request.user, data=request.data)
        if serializer.is_valid():
            serializer = PeerSerializer(serializer.save())
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class UserProfileView(APIView):
    def get(self, request):
        wallet_hash = request.headers.get('wallet_hash')
        if wallet_hash is None:
            return Response({'error': 'wallet_hash is required'}, status=status.HTTP_400_BAD_REQUEST)

        user = None
        is_arbiter = False

        arbiter = Arbiter.objects.filter(wallet_hash=wallet_hash)
        if arbiter.exists():
            user = ArbiterProfileSerializer(arbiter.first()).data
            is_arbiter = True
        
        if not is_arbiter:
            peer = Peer.objects.filter(wallet_hash=wallet_hash)
            if peer.exists():    
                user = PeerProfileSerializer(peer.first()).data
            
        response = {
            "is_arbiter": is_arbiter,
            "user": user
        }

        return Response(response, status.HTTP_200_OK)