"""Server-side enforcement of the existing P2P feature controls."""

from functools import wraps

from django.http import JsonResponse

from rampp2p.models import FeatureControl


def p2p_maintenance_guard(handler):
    """Pause P2P HTTP access before invoking a routed view."""
    @wraps(handler)
    def guarded(request, *args, **kwargs):
        if FeatureControl.objects.filter(
            name=FeatureControl.Type.P2P_MAINTENANCE, is_enabled=True,
        ).exists():
            response = JsonResponse({
                'error': 'P2P is temporarily under maintenance. Please do not fund existing orders.',
                'code': 'p2p_maintenance',
                'feature': FeatureControl.Type.P2P_MAINTENANCE,
            }, status=503)
            response['Cache-Control'] = 'no-store'
            return response
        return handler(request, *args, **kwargs)
    return guarded


def require_p2p_feature(feature):
    """Check the database on each call; absent controls fail closed."""
    def decorate(handler):
        @wraps(handler)
        def guarded(self, request, *args, **kwargs):
            if not FeatureControl.objects.filter(name=feature, is_enabled=True).exists():
                response = JsonResponse({
                    'error': 'This P2P feature is temporarily unavailable.',
                    'code': 'p2p_feature_disabled',
                    'feature': feature,
                }, status=503)
                response['Cache-Control'] = 'no-store'
                return response
            return handler(self, request, *args, **kwargs)
        return guarded
    return decorate
