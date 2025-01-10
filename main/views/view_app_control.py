from django.http import JsonResponse
from main.models import AppControl

def check_app_control(request):
    app_status = {
        app.name: app.is_enabled
        for app in AppControl.objects.all()
    }
    return JsonResponse(app_status)