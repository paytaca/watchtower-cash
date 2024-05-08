from django.http import Http404
from rest_framework.response import Response
from rest_framework import (
    viewsets,
    mixins,
)

from main.serializers import WalletShardSerializer


class WalletShardViewSet(
    viewsets.GenericViewSet,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin
):
    serializer_class = WalletShardSerializer
    lookup_field = 'shard'
    http_method_names = ['post', 'get', 'head']

    def get_model(self):
        return self.serializer_class.Meta.model
    
    def get_object(self):
        shard = self.kwargs.get('shard', '')
        return self.get_model().objects.filter(shard=shard)

    def create(self, request, *args, **kwargs):
        shard_check = self.get_object()

        if not shard_check.exists():
            return super().create(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        # first_identifier = kwargs.get('first_identifier', None)
        # second_identifier = kwargs.get('second_identifier', None)
        
        # shard_check = self.get_model().objects.filter(
        #     first_identifier=first_identifier,
        #     second_identifier=second_identifier
        # )

        # data = None
        # if shard_check.exists():
        #     data = shard_check.first().get_shard()

        # adjust to use first and second identifiers
        shard_check = self.get_object()

        data = None
        if shard_check.exists():
            data = shard_check.first()
        else:
            return Response(data={'message': 'No data found' }) # add status

        serializer = self.serializer_class(data)
        return Response(data=serializer.data)