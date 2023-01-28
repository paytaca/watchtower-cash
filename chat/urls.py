from rest_framework import routers
from django.urls import re_path
from chat.views import ChatIdentityViewSet, ConversationView

router = routers.DefaultRouter()
router.register(r"identity", ChatIdentityViewSet, basename="chat-identity")

urlpatterns = router.urls + [
    re_path('^conversations/(?P<address>.+)/$', ConversationView.as_view())
]
