from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from rest_framework import routers
from main import views


router = routers.DefaultRouter()
router.register(r"slp_address", views.SlpAddressViewSet)
router.register(r"subscription", views.SubscriptionViewSet)
router.register(r"users", views.UserViewSet)
router.register(r"token", views.TokenViewSet)
router.register(r"transaction", views.TransactionViewSet)
urlpatterns = router.urls