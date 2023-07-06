from django.urls import path

from paytacagifts import views

urlpatterns = router.urls + [
    path('<str:wallet_hash>/list', views.GiftsListViewset.as_view(), name="broadcast-pos-payment"),
    path('<str:wallet_hash>/create', views.GiftsCreateViewset.as_view(), name="broadcast-pos-payment"),
    path('<str:gift_code_hash>/claim/', views.CampaignViewSet.as_view({'post': 'claim_gift'}), name='claim-gift'),
    path('<str:gift_code_hash>/recover/', views.CampaignViewSet.as_view({'post': 'recover_gift'}), name='recover-gift'),
]
