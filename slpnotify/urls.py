"""x URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from django.conf.urls.static import static
from django.conf import settings
from django.conf.urls import url
from django.urls import path, include
from django.views.decorators.csrf import csrf_exempt

from rest_framework.authtoken import views
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

from main.urls import urlpatterns as main_urls

from main.views import ( 
    SlackDirectMessageView,
    SlackNotificationView,
    SetAddressView,
    TelegramBotView, 
    TelegramSendtoView
)

schema_view = get_schema_view(
   openapi.Info(
      title="SLPNotify",
      default_version='v1',
      description="Reliable SLP transaction notifications",
      contact=openapi.Contact(name="Support",url="https://t.me/slpnotify")
   ),
   public=True,
   permission_classes=(permissions.AllowAny,),
)


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(main_urls)),
    path('set-address/', SetAddressView.as_view(), name='setaddress'),
    path('webhooks/telegram/', csrf_exempt(TelegramBotView.as_view()), name="telegram-webhook"),
    path('telegram/notify/', csrf_exempt(TelegramSendtoView.as_view()), name="telegram-notify"),
    path('slack/dm/', csrf_exempt(SlackDirectMessageView.as_view()), name='slack-dm'),
    path('slack/notify/', csrf_exempt(SlackNotificationView.as_view()), name='slack-notify'),
    url(r'^api/swagger(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    url(r'^api/redoc/$', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    url(r'', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
]
