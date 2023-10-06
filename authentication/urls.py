from django.urls import path

from authentication.views import *

urlpatterns = [
    path('nonce/<str:wallet_hash>', AuthNonceView.as_view(), name='nonce'),
    path('login', LoginView.as_view(), name='login'),   
]