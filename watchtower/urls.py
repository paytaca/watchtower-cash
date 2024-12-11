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
from django.views.generic import TemplateView

from rest_framework.authtoken import views
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from main.urls import main_urls, test_urls
from paytacapos.urls import urlpatterns as paytacapos_urlpatterns
from paymentvault.urls import urlpatterns as paymentvault_urlpatterns
from smartbch.urls import urlpatterns as sbch_urlpatterns
from anyhedge.urls import urlpatterns as anyhedge_urlpatterns
from chat.urls import urlpatterns as chat_urlpatterns
from notifications.urls import urlpatterns as notifications_urlpatterns
from jpp.urls import urlpatterns as jpp_urlpatterns
from django.conf.urls.static import static
from django.conf import settings
from ramp.urls import urlpatterns as ramp_urlpatterns
from rampp2p.urls import urlpatterns as ramp_p2p_urlpatterns
from paytacagifts.urls import urlpatterns as paytacagifts_urlpatterns
from cts.urls import urlpatterns as cts_urlpatterns
from authentication.urls import urlpatterns as auth_urlpatterns
from stablehedge.urls import urlpatterns as stablehedge_urlpatterns

from main.views import TelegramBotView


schema_view = get_schema_view(
   openapi.Info(
      title="watchtower",
      default_version='v1',
      url='https://watchtower.cash/',
      description="Instant and reliable infrastructure connecting you to the Bitcoin Cash blockchain",
      contact=openapi.Contact(name="Support",url="https://t.me/WatchTowerCash")
   ),
   public=True,
   permission_classes=(permissions.AllowAny,),
)


urlpatterns = [
    path('', TemplateView.as_view(template_name="main/index.html")),
    path(
        '.well-known/apple-app-site-association',
        TemplateView.as_view(
            template_name="main/apple-app-site-association.json",
            content_type="application/json"
        )
    ),
    path(
        '.well-known/assetlinks.json',
        TemplateView.as_view(
            template_name="main/assetlinks.json",
            content_type="application/json"
        )
    ),
    path('admin/', admin.site.urls),
    path('api/', include(main_urls)),
    path('api/smartbch/', include(sbch_urlpatterns)),
    path('api/paytacapos/', include(paytacapos_urlpatterns)),
    path('api/payment-vaults/', include(paymentvault_urlpatterns)),
    path('api/anyhedge/', include(anyhedge_urlpatterns)),
    path('api/chat/', include(chat_urlpatterns)),
    path('api/push-notifications/', include(notifications_urlpatterns)),
    path('api/jpp/', include(jpp_urlpatterns)),
    path('api/ramp/', include(ramp_urlpatterns)),
    path('api/ramp-p2p/', include(ramp_p2p_urlpatterns)),
    path('api/cts/', include(cts_urlpatterns)),
    path('api/auth/', include(auth_urlpatterns)),
    path('api/stablehedge/', include(stablehedge_urlpatterns)),
    path(r'test/', include(test_urls)),
    path('webhooks/telegram/', csrf_exempt(TelegramBotView.as_view()), name="telegram-webhook"),
    url(r'^api/swagger(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    url(r'^api/redoc/$', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    url(r'api/docs/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui')
]


urlpatterns += [
    path('api/', include(paytacagifts_urlpatterns)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    import re
    from django.urls import re_path
    from django.conf import settings
    from rampp2p.views.views_utils import media_proxy_view
    
    base_media_url = settings.MEDIA_URL.strip("/")
    urlpatterns += [
        re_path(r'^'+ re.escape(base_media_url) + r'/(?P<path>.*)$', media_proxy_view),
        path(base_media_url, media_proxy_view),
    ]
