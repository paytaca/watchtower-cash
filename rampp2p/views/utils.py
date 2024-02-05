from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from main.utils.subscription import save_subscription

from rampp2p.models import MarketRate
from rampp2p.serializers import MarketRateSerializer

import logging
logger = logging.getLogger(__name__)
    
class MarketRates(APIView):
    def get(self, request):
        queryset = MarketRate.objects.all()
        currency = request.query_params.get('currency')
        response = {}
        if currency is not None:
            queryset = MarketRate.objects.filter(currency=currency)
            if (queryset.exists()):
                response = MarketRateSerializer(queryset.first()).data
        else:
            response = MarketRateSerializer(queryset, many=True).data
        return Response(response, status.HTTP_200_OK)
    
class SubscribeContractAddress(APIView):
    def post(self, request):
        address = request.data.get('address')
        subscriber_id = request.data.get('subscriber_id')
        if address is None:
            return Response({'error': 'address is required'}, status.HTTP_400_BAD_REQUEST)
        
        created = save_subscription(address, subscriber_id)
        return Response({'success': created}, status.HTTP_200_OK)