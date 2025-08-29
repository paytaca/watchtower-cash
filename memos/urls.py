from rest_framework import routers
from django.urls import re_path, path
from django.views.decorators.csrf import csrf_exempt

from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)


from .views import (
    MemoView,
    RegisterView
)

router = routers.DefaultRouter()

urlpatterns = router.urls + [
    re_path('auth/', TokenObtainPairView.as_view(), name="memo-auth" ),
    re_path('refresh/', TokenRefreshView.as_view(), name="refresh-auth"),
    re_path('register/', RegisterView.as_view(), name="register-user"),
    re_path('', MemoView.as_view()),
    # path(r'^(?P<pk>\d+)/$', MemoView.as_view()),
    # re_path('/<int:pk>/', MemoView.as_view()),
    # re_path('shift', RampShiftView.as_view(), name="ramp-shift"),    
    # re_path(r'^history/(?P<wallet_hash>[\w+:]+)/$', RampShiftHistoryView.as_view(), name='shift-history'),
    # re_path('expire', RampShiftExpireView.as_view(), name='shift-expire'),
    # path('create-shift', RampCreateShift.as_view(), name='create-shift')
    # re_path('history', RampShiftHistoryView.as_view(), name='shift-history')
]