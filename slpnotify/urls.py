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
    SignIn, 
    SignOut, 
    SlackBotView,
    SetAddressView
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
    path('signin/', SignIn.as_view(), name='signin'),
    path('signout/', SignOut.as_view(), name='signout'),
    path('set-address/', SetAddressView.as_view(), name='setaddress'),
    path('webhook/slack/', csrf_exempt(SlackBotView.as_view()), name='slack'),
    path('accounts/login/', admin.site.urls),
    path('api/v1/', include(main_urls)),
    url(r'^api/swagger(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    url(r'^api/redoc/$', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    url(r'', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
]
