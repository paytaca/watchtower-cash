from django.urls import path

from authentication.views import *

urlpatterns = [
    path('otp', AuthNonceView.as_view(), name='otp'),
    path('login', LoginView.as_view(), name='login'),   
]