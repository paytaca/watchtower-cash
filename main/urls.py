from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from rest_framework import routers
from main import views

app_name = "main"


router = routers.DefaultRouter()
router.register(r"slp_address", views.SlpAddressViewSet)
router.register(r"token", views.TokenViewSet)
router.register(r"transaction", views.TransactionViewSet)
router.register(r"auth", views.AuthViewSet,basename='auth')
router.register(r"subscription", views.SubscriptionViewSet, basename='subscription')

urlpatterns = router.urls

