from rest_framework import viewsets, mixins

from purelypeer.serializers import CreateCashdropNftPairSerializer
from purelypeer.models import CashdropNftPair


class CashdropNftPairViewSet(viewsets.GenericViewSet, mixins.CreateModelMixin):
    queryset = CashdropNftPair.objects.all()
    serializer_class = CreateCashdropNftPairSerializer
