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
    http_method_names = ['get', 'patch', 'head']

    def get_model(self):
        return self.serializer_class.Meta.model
    
    # def get_queryset(self):
    #     return self.get_model().objects.filter(shard=self.request.shard)

    # def create(self, request):
    #   pass

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
        shard = kwargs.get('pk', '')
        shard_check = self.get_model().objects.filter(shard=shard)

        data = None
        if shard_check.exists():
            data = shard_check.first()
        else:
            return Response(data={'message': 'No data found' }) # add status

        serializer = self.serializer_class(data)
        return Response(data=serializer.data)

    def update(self, request, *args, **kwargs):
        # try:
        #     self.get_object()
        # except Http404:
        #    shard = self.kwargs['shard']
        #    self.get_model().objects.update_or_create(shard=shard)

        return super().update(request, *args, **kwargs)