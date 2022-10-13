from django_filters import rest_framework as filters

from .models import PosDevice

class PosDevicetFilter(filters.FilterSet):
    class Meta:
        model = PosDevice
        fields= [
            "wallet_hash",
        ]
