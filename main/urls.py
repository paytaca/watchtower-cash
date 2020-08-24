from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from rest_framework import routers
from main.views import (
	view_account,
    view_address,
    view_auth,
    view_home,
    view_slp,
    view_token
)


router = routers.DefaultRouter()
router.register(r"account", view_account.CreateAccountSerializer, basename="shipping")
# router.register(r"account/(?P<user_uuid>[^/.]+)/", view_account.CreateAccountSerializer, basename="shipping")

# router.register(r"users", UserViewSet, basename="users")
# router.register(r"users/(?P<user_uuid>[^/.]+)/addresses", AddressViewSet, basename="addresses")


urlpatterns = router.urls + [
    path('addresses/', csrf_exempt(AddressView.as_view()), name='addresses'),
    path('chatbot/oauth/', csrf_exempt(OAuthView.as_view()), name='facebook-oauth'),
]
