from django.urls import path, include

from paytacagifts import views
from rest_framework_extensions.routers import ExtendedDefaultRouter

router = ExtendedDefaultRouter()
router.register('gifts', views.GiftViewSet, 'gift'),
router.register('campaign', views.CampaignViewSet, 'campaign'),

urlpatterns = [
    path('', include(router.urls)),
]
