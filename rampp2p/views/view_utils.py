from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response

from pathlib import Path
from django.conf import settings
from django.http import FileResponse
from django.http import HttpResponse, JsonResponse

from main.utils.subscription import save_subscription
from rampp2p.utils.fees import get_trading_fees

from rampp2p.models import MarketPrice, AppVersion, FeatureControl
from rampp2p.serializers import MarketPriceSerializer
from decimal import Decimal

import logging
logger = logging.getLogger(__name__)

def check_feature_control(request):
    feature_status = {
        feature.name: feature.is_enabled
        for feature in FeatureControl.objects.all()
    }
    return JsonResponse(feature_status)
    
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

class MarketPrices(APIView):
    def get(self, request):
        queryset = MarketPrice.objects.all()
        currency = request.query_params.get('currency')
        response = {}
        if currency is not None:
            queryset = MarketPrice.objects.filter(currency=currency)
            if (queryset.exists()):
                response = MarketPriceSerializer(queryset.first()).data
        else:
            response = MarketPriceSerializer(queryset, many=True).data
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
    try:
        relative_path = Path(path)
        if relative_path.is_absolute():
            return HttpResponse(status=404)

        media_root = Path(settings.MEDIA_ROOT).resolve(strict=True)
        file_path = (media_root / relative_path).resolve(strict=True)
        # Resolve symlinks before checking containment. A string-prefix check
        # would also allow sibling directories such as "media-private".
        file_path.relative_to(media_root)
        if not file_path.is_file():
            return HttpResponse(status=404)
        return FileResponse(file_path.open('rb'))
    except (OSError, ValueError, RuntimeError):
        # Missing/inaccessible files, invalid paths and symlink loops all look
        # like an unavailable media file; do not expose filesystem details.
        return HttpResponse(status=404)
