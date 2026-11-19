from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response

import os
from django.conf import settings
from django.http import FileResponse
from django.http import HttpResponse, JsonResponse, HttpResponseNotAllowed

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
    """Serve a file from MEDIA_ROOT without letting the URL escape it.

    Media is only ever read, so anything but GET/HEAD is rejected, the
    caller-supplied path is normalised, and the resolved target (symlinks
    included) must still live inside MEDIA_ROOT. Treat every failure as an
    indistinguishable 404 so the endpoint cannot be used to probe the disk.
    """
    if request.method not in ("GET", "HEAD"):
        return HttpResponseNotAllowed(["GET", "HEAD"])

    path = kwargs.get("path", "").replace("\\", "/")
    if path.endswith("/"): path = path[:-1]

    # Check before touching the filesystem: `os.path.join` discards the base
    # for an absolute path (`/etc/passwd`), and `..` segments walk upwards.
    # A NUL byte would raise from the filesystem calls below, so reject it too.
    if not path or os.path.isabs(path) or ".." in path.split("/") or "\x00" in path:
        return HttpResponse(status=404)

    media_root = os.path.realpath(settings.MEDIA_ROOT)

    try:
        file_path = os.path.realpath(os.path.join(media_root, path))
    except (OSError, ValueError):
        return HttpResponse(status=404)

    # `realpath` also resolves symlinks, so a link planted inside the media
    # tree cannot point back out of it. `commonpath` is path-aware, unlike a
    # string prefix check (`/srv/media-secrets` vs `/srv/media`).
    try:
        within_media_root = os.path.commonpath([media_root, file_path]) == media_root
    except ValueError:
        # Mixed absolute/relative paths or different drives.
        within_media_root = False

    if not within_media_root or not os.path.isfile(file_path):
        return HttpResponse(status=404)

    return FileResponse(open(file_path, 'rb'), as_attachment=True)
