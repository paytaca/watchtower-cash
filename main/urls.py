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

# urlpatterns=[
#     path('', admin.site.urls),
#     path('login/', Loginpage.as_view(), name='loginpage'),
#     path('logout/', Logout.as_view(), name='logout'),
#     path('account/', Account.as_view(), name='account'),
#     path('setuptokens/', SetupToken.as_view(), name='setuptoken'),
#     path('setupslpaddresses/', SetupSLPAddress.as_view(), name='setupslpaddress'),
#     path('set-address/', SetAddressView.as_view()),
#     url(r'^api-token-auth/', views.obtain_auth_token),
#     url(r'^swagger(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0), name='schema-json'),
#     url(r'^swagger/$', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
#     url(r'^redoc/$', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
# ] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)