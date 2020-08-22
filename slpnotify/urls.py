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
from rest_framework.authtoken import views
from main.views import (
  Loginpage,   
  Logout,
  Account,
  SetupToken,
  SetupSLPAddress,
  SetAddressView
)

urlpatterns=[
    path('', admin.site.urls),
    path('login/', Loginpage.as_view(), name='loginpage'),
    path('logout/', Logout.as_view(), name='logout'),
    path('account/', Account.as_view(), name='account'),
    path('setuptokens/', SetupToken.as_view(), name='setuptoken'),
    path('setupslpaddresses/', SetupSLPAddress.as_view(), name='setupslpaddress'),
    path('set-address/', SetAddressView.as_view()),
    url(r'^api-token-auth/', views.obtain_auth_token),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)