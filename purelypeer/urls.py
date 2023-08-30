from rest_framework import routers

from .views import CashdropNftPairViewSet

router = routers.DefaultRouter()
router.register("cashdrop_nft_pairs", CashdropNftPairViewSet)

urlpatterns = router.urls
