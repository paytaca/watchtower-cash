from django.http import Http404
from rest_framework import (
    viewsets,
    mixins,
)

from main.models import Wallet
from main.serializers import WalletPreferencesSerializer


class WalletPreferencesViewSet(
    viewsets.GenericViewSet,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
):
    lookup_field = "wallet__wallet_hash"
    serializer_class = WalletPreferencesSerializer

    http_method_names = ['get', 'patch', 'head']

    def get_model(self):
        return self.serializer_class.Meta.model

    def get_queryset(self):
        return self.get_model().objects.prefetch_related("wallet").all()

    def update(self, request, *args, **kwargs):
        try:
            self.get_object()
        except Http404:
            wallet_hash = self.kwargs[self.lookup_field]
            try:
                wallet = Wallet.objects.get(wallet_hash=wallet_hash)
                self.get_model().objects.get_or_create(wallet=wallet)
            except Wallet.DoesNotExist:
                raise Http404

        return super().update(request, *args, **kwargs)