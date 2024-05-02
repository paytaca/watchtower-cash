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
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin
):
    serializer_class = WalletShardSerializer

    def get_model(self):
        return self.serializer_class.Meta.model

    # def create(self, request):
    #   pass

    def retrieve(self, request, pk=None, *args, **kwargs):
        first_identifier = kwargs.get('first_identifier', None)
        second_identifier = kwargs.get('second_identifier', None)
        
        shard_check = self.get_model().objects.filter(
            first_identifier=first_identifier,
            second_identifier=second_identifier
        )

        data = None
        if shard_check.exists():
            data = shard_check.first().get_shard()

        serializer = self.serializer_class(data=data)
        return Response(data=serializer.initial_data)

    def update(self, request, pk=None, *args, **kwargs):
        try:
            self.get_object()
        except Http404:
           shard = self.kwargs['shard']
           self.get_model().objects.update_or_create(shard=shard)

        return super().update(request, *args, **kwargs)