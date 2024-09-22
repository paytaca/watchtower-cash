from django.http import JsonResponse
from main.models import AppVersion

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