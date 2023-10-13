from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rampp2p.models import MarketRate
from rampp2p.serializers import MarketRateSerializer
# from main.utils.subscription import new_subscription, remove_subscription


import logging
logger = logging.getLogger(__name__)
    
class MarketRates(APIView):
    def get(self, request):
        queryset = MarketRate.objects.all()
        currency = request.query_params.get('currency')
        if currency is not None:
            queryset = MarketRate.objects.filter(currency=currency)
        serializer = MarketRateSerializer(queryset, many=True)
        return Response(serializer.data, status.HTTP_200_OK)