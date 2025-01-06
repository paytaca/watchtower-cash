from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response

import os
from django.conf import settings
from django.http import FileResponse
from django.http import HttpResponse, JsonResponse

from main.utils.subscription import save_subscription
from rampp2p.utils.fees import get_trading_fees

from rampp2p.models import MarketRate, AppVersion, FeatureToggle
from rampp2p.serializers import MarketRateSerializer
from decimal import Decimal

import logging
logger = logging.getLogger(__name__)

def feature_toggles(request):
    toggles = {
        toggle.feature_name: toggle.is_enabled
        for toggle in FeatureToggle.objects.all()
    }
    return JsonResponse(toggles)
    
def check_app_version(request, platform=None):
    if platform:
        version_info = AppVersion.objects.filter(platform=platform).order_by('-release_date').first()
    else:
        version_info = AppVersion.objects.order_by('-release_date').first()
    
    if version_info:
        response_data = {
            'latest_version': version_info.latest_version,
            'min_required_version': version_info.min_required_version,
            'release_date': version_info.release_date,
            'notes': version_info.notes
        }
    else:
        response_data = {
            'error': 'No version information available'
        }
    
    return JsonResponse(response_data)

class ContractFeeCalculation(APIView):
    def get(self, request):
        trade_amount = request.query_params.get('sats_trade_amount', None)
        if trade_amount:
            trade_amount = Decimal(trade_amount)
        _, fees = get_trading_fees(trade_amount=trade_amount)
        return Response(fees, status=status.HTTP_200_OK)

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
    
def media_proxy_view(request, *args, **kwargs):
    path = kwargs.get("path", "")
    if path.endswith("/"): path = path[:-1]

    file_path = os.path.join(settings.MEDIA_ROOT, path)

    if os.path.exists(file_path):
        return FileResponse(open(file_path, 'rb'))
    else:
        return HttpResponse(status=404)