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
from main.views import (
  Loginpage,   
  Home,
  Logout,
  Account,
  Token
)

urlpatterns = [
    path('login/', Loginpage.as_view(), name='loginpage'),
    path('admin/', admin.site.urls),
    path('logout/', Logout.as_view(), name='logout'),
    path('account/', Account.as_view(), name='account'),
    path('tokens/', Token.as_view(), name='token'),
    path('', Home.as_view(), name='home'),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
