from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response

from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.conf import settings
from django.db.models import Q
from authentication.token import TokenAuthentication
from rampp2p.viewcodes import ViewCode
from rampp2p.models import Arbiter, Peer
from rampp2p.serializers import ArbiterSerializer
from rampp2p.utils.signature import verify_signature, get_verification_headers
from datetime import datetime, timedelta

class ArbiterListCreate(APIView):
    authentication_classes = [TokenAuthentication]

    def get(self, request):
        queryset = Arbiter.objects.filter(Q(is_disabled=False) & (Q(inactive_until__isnull=True) | Q(inactive_until__lte=datetime.now())))

        # Filter by currency. Default to arbiter for PHP if not set
        currency = request.query_params.get('currency') or 'PHP'
        if not currency:
            return Response({'error': 'currency is required'}, status.HTTP_400_BAD_REQUEST)
        queryset = queryset.filter(fiat_currencies__symbol=currency)

        # Filter by arbiter id
        id = request.query_params.get('id')
        if id:
            queryset = queryset.filter(id=id)

        serializer = ArbiterSerializer(queryset, many=True)
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

        serialized_arbiter = ArbiterSerializer(data=data)
        if not serialized_arbiter.is_valid():
            return Response(serialized_arbiter.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            serialized_arbiter = ArbiterSerializer(serialized_arbiter.save())
        except IntegrityError:
            return Response({'error': 'arbiter with wallet_hash already exists'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serialized_arbiter.data, status=status.HTTP_200_OK)

class ArbiterDetail(APIView):
    authentication_classes = [TokenAuthentication]
    
    def get(self, request):
        arbiter_id = request.data.get('arbiter_id')
        wallet_hash = request.user.wallet_hash
        try:
            arbiter = None
            if arbiter_id:
                arbiter = Arbiter.objects.get(pk=arbiter_id)
            else:
                arbiter = Arbiter.objects.get(wallet_hash=wallet_hash)
        except Arbiter.DoesNotExist as err:
            return Response({'error': err.args[0]}, status=400)
        return Response(ArbiterSerializer(arbiter).data, status=200)
    
    def patch(self, request):
        data = request.data.copy()
        inactive_hours = request.data.get('inactive_hours')
        if inactive_hours:
            data['inactive_until'] = datetime.now() + timedelta(hours=inactive_hours)
        serializer = ArbiterSerializer(request.user, data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer = ArbiterSerializer(serializer.save())
        return Response(serializer.data, status=status.HTTP_200_OK)        
