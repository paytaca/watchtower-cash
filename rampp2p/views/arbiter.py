from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError

from rampp2p.models import Arbiter, Peer
from rampp2p.serializers import ArbiterWriteSerializer, ArbiterReadSerializer

from rampp2p.viewcodes import ViewCode
from rampp2p.utils.signature import verify_signature, get_verification_headers

from django.conf import settings
from authentication.token import TokenAuthentication

class ArbiterListCreate(APIView):
    authentication_classes = [TokenAuthentication]

    def get(self, request):
        queryset = Arbiter.objects.filter(is_disabled=False)
        id = request.query_params.get('id')
        if id is not None:
            queryset = queryset.filter(id=id)
        serializer = ArbiterReadSerializer(queryset, many=True)
        return Response(serializer.data, status.HTTP_200_OK)
    
    def post(self, request):
        public_key = request.data.get('public_key')
        if public_key is None:
            return Response({'error': 'public_key is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # validate signature
        signature, timestamp, wallet_hash = get_verification_headers(request)
        message = ViewCode.ARBITER_CREATE.value + '::' + timestamp
        verify_signature(wallet_hash, signature, message, public_key=public_key)
        
        peer = Peer.objects.filter(wallet_hash=wallet_hash)
        if peer.exists():
            return Response({'error': 'Users cannot be both Peer and Arbiter'}, status=status.HTTP_400_BAD_REQUEST)
        
        data = request.data.copy()
        data['wallet_hash'] = wallet_hash

        serialized_arbiter = ArbiterWriteSerializer(data=data)
        if not serialized_arbiter.is_valid():
            return Response(serialized_arbiter.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            serialized_arbiter = ArbiterReadSerializer(serialized_arbiter.save())
        except IntegrityError:
            return Response({'error': 'arbiter with wallet_hash already exists'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serialized_arbiter.data, status=status.HTTP_200_OK)

class ArbiterDetail(APIView):
    authentication_classes = [TokenAuthentication]

    def get(self, request):
        try:
            public_key = request.query_params.get('public_key')
            if public_key is None:
                raise ValidationError('public_key is required')
            
            # validate signature
            signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.ARBITER_GET.value + '::' + timestamp
            verify_signature(wallet_hash, signature, message, public_key=public_key)

        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_200_OK)

        response = {}
        try:
            arbiter = Arbiter.objects.get(wallet_hash=wallet_hash)
            response['arbiter'] = ArbiterReadSerializer(arbiter).data
        except Arbiter.DoesNotExist:
            response['arbiter'] = None
        
        return Response(response, status=status.HTTP_200_OK)

    def put(self, request):
        try:
            public_key = request.data.get('public_key')
            if public_key is None:
                raise ValidationError('public_key is required')
            
            # validate signature
            signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.ARBITER_UPDATE.value + '::' + timestamp
            verify_signature(wallet_hash, signature, message, public_key=public_key)

        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)

        try:
            arbiter = Arbiter.objects.get(wallet_hash=wallet_hash)
            
            new_public_key = request.data.get('public_key')
            if new_public_key is not None:
                arbiter.public_key = new_public_key
            
            new_address = request.data.get('address')
            if new_address is not None:
                arbiter.address = new_address
            
            new_name = request.data.get('name')
            if new_name is not None:
                arbiter.name = new_name

            arbiter.save()
        except (Arbiter.DoesNotExist, Exception) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        
        serialized_arbiter = ArbiterReadSerializer(arbiter).data
        return Response(serialized_arbiter, status=status.HTTP_200_OK)

class ArbiterConfig(APIView):
    authentication_classes = [TokenAuthentication]
    
    """
    This view allows users to disable or enable an arbiter instance.
    """
    def post(self, request):
        try:
            # validate signature
            signature, timestamp, wallet_hash = get_verification_headers(request)

            # validate perms: caller must be servicer
            if wallet_hash != settings.SERVICER_WALLET_HASH:
                raise ValidationError('caller must be servicer')
            
            message = ViewCode.ARBITER_CONFIG.value + '::' + timestamp
            verify_signature(wallet_hash, signature, message, public_key=settings.SERVICER_PK)
            

        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
        
        disable = request.data.get('disable')
        if disable is None:
            return Response({'error': 'disable field is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            arbiter = Arbiter.objects.get(wallet_hash=wallet_hash)
            arbiter.is_disabled = disable
            arbiter.save()

            serialized_arbiter = ArbiterReadSerializer(arbiter)

        except Arbiter.DoesNotExist as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(serialized_arbiter.data, status=status.HTTP_200_OK)