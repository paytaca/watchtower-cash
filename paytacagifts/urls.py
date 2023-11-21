from django.urls import path, include, re_path

from paytacagifts import views

urlpatterns = [
    path('campaigns/<str:wallet_hash>/list/', views.CampaignViewSet.as_view({'get': 'list_campaigns'}), name='campaign-list'),
    path('gifts/<str:wallet_hash>/list/', views.GiftViewSet.as_view({'get': 'list_gifts'}), name='gift-list'),
    path('gifts/<str:wallet_hash>/create/', views.GiftViewSet.as_view({'post': 'create'}), name='gift-create'),
    path('gifts/<str:gift_code_hash>/claim', views.GiftViewSet.as_view({'post': 'claim'}), name='gift-claim'),
    path('gifts/<str:gift_code_hash>/recover', views.GiftViewSet.as_view({'post': 'recover'}), name='gift-recover'),
    re_path(r"^claim/$", views.GiftClaimView.as_view(),name='claim'),
]
