from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rampp2p.models import Arbiter
from rampp2p.serializers import ArbiterSerializer

class ArbiterView(APIView):
    def get(self, request):
        queryset = Arbiter.objects.all()
        
        id = request.query_params.get('id')
        if id is not None:
            queryset = queryset.filter(id=id)

        wallet_hash = request.headers.get('wallet_hash')
        if wallet_hash is not None:
            queryset = queryset.filter(wallet_hash=wallet_hash)

        serializer = ArbiterSerializer(queryset, many=True)
        return Response(serializer.data, status.HTTP_200_OK)
