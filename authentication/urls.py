from django.urls import path

from authentication.views import *

urlpatterns = [
    path('', UserView.as_view(), name='auth-user'),
    path('wallet', WalletView.as_view(), name='auth-wallet'),
    path('otp/main', AuthNonceView.as_view(), name='main-otp'),
    path('otp/peer', AuthNonceView.as_view(), name='ramp-peer-otp'),
    path('otp/arbiter', AuthNonceView.as_view(), name='ramp-arbiter-otp'),
    path('login/main', LoginView.as_view(), name='main-login'),
    path('login/peer', LoginView.as_view(), name='ramp-peer-login'),
    path('login/arbiter', LoginView.as_view(), name='ramp-arbiter-login'),
    path('revoke', RevokeTokenView.as_view(), name='ramp-revoke-token')
]