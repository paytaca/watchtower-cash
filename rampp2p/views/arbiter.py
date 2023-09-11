from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.core.exceptions import ValidationError

from rampp2p.models import Arbiter
from rampp2p.serializers import ArbiterSerializer

from rampp2p.viewcodes import ViewCode
from rampp2p.utils.signature import verify_signature, get_verification_headers

class ArbiterList(APIView):
    def get(self, request):
        queryset = Arbiter.objects.all()
        id = request.query_params.get('id')
        if id is not None:
            queryset = queryset.filter(id=id)
        serializer = ArbiterSerializer(queryset, many=True)
        return Response(serializer.data, status.HTTP_200_OK)

class ArbiterDetail(APIView):
    def get(self, request):
        wallet_hash = request.headers.get('wallet_hash')
        if wallet_hash is None:
            return Response({'error': 'wallet_hash is None'}, status=status.HTTP_403_FORBIDDEN)
        try:
            # validate signature
            signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.ARBITER_GET.value + '::' + timestamp
            verify_signature(wallet_hash, signature, message)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)

        response = {}
        try:
            arbiter = Arbiter.objects.get(wallet_hash=wallet_hash)
            response['arbiter'] = ArbiterSerializer(arbiter).data
        except Arbiter.DoesNotExist:
            response['arbiter'] = None
        
        return Response(response, status=status.HTTP_200_OK)