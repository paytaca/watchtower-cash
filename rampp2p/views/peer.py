from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import Http404
from django.utils import timezone
from authentication.token import TokenAuthentication
from authentication.serializers import UserSerializer
from rampp2p.models import Peer, Arbiter, ReservedName
from rampp2p.serializers import (
    PeerSerializer, 
    PeerCreateSerializer,
    PeerUpdateSerializer,
    PeerProfileSerializer,
    ArbiterSerializer
)
from rampp2p.viewcodes import ViewCode
from rampp2p.utils.signature import verify_signature, get_verification_headers

class PeerCreateView(APIView):
    def post(self, request):
        try:
            signature, timestamp, wallet_hash = get_verification_headers(request)
            public_key = request.headers.get('public_key')
            
            message = ViewCode.PEER_CREATE.value + '::' + timestamp
            verify_signature(wallet_hash, signature, message, public_key=public_key)
        except Exception as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

        arbiter = Arbiter.objects.filter(wallet_hash=wallet_hash)
        if arbiter.exists():
            return Response({'error': 'Users cannot be both Peer and Arbiter'}, status=status.HTTP_400_BAD_REQUEST)

        # check if username is reserved
        prefix = 'reserved-'
        reserved = None
        username = request.data.get('name')
        duplicate_name_error = False
        if (username.startswith(prefix)):
            subset_key = username[len(prefix):]
            reserved_name = ReservedName.objects.filter(key=subset_key)
            if reserved_name.exists():
                # accept key if reserved name is not yet associated with a Peer
                if reserved_name.first().peer is None:
                    reserved = reserved_name.first()
                    username = reserved.name
                else:
                    duplicate_name_error = True
            else:
                return Response({'error': 'no such reserved username'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            # check if username already exists
            if (Peer.objects.filter(name__iexact=username).exists() or
                ReservedName.objects.filter(name__iexact=username).exists()):
                duplicate_name_error = True
        
        if duplicate_name_error:
            return Response({'error': 'similar username already exists'}, status=status.HTTP_400_BAD_REQUEST)
        
        # create new Peer instance
        data = request.data.copy()
        data['name'] = username
        data['wallet_hash'] = wallet_hash
        data['public_key'] = public_key
        
        serializer = PeerCreateSerializer(data=data)
        if serializer.is_valid():
            peer = serializer.save()
            serializer = PeerSerializer(peer)
            if reserved:
                reserved.peer = peer
                reserved.redeemed_at = timezone.now()
                reserved.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class PeerDetailView(APIView):
    authentication_classes = [TokenAuthentication]
    
    def get(self, request):
        id = request.query_params.get('id')
        try:
            peer = Peer.objects.get(id=id)
        except Peer.DoesNotExist:
            raise Http404
        serializer = PeerSerializer(peer)
        return Response(serializer.data, status.HTTP_200_OK)

    def put(self, request):        
        serializer = PeerUpdateSerializer(request.user, data=request.data)
        if serializer.is_valid():
            peer = serializer.save()
            user_info = {
                'id': peer.id,
                'chat_identity_id': peer.chat_identity_id,
                'public_key': peer.public_key,
                'name': peer.name,
                'address': peer.address,
                'address_path': peer.address_path
            }
            return Response(UserSerializer(user_info).data, status=status.HTTP_200_OK)
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
            user = ArbiterSerializer(arbiter.first()).data
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
    