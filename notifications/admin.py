from django.db import models
from django.contrib import admin

from .models import DeviceWallet

# Register your models here.
class HasNoDeviceFilter(admin.SimpleListFilter):
    title = "has linked device"
    parameter_name = "has_linked_device"

    def lookups(self, request, model_admin):
        return (
            ('1', 'Yes'),
            ('0', 'No'),
        )

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        if self.value() == "1":
            queryset = queryset.filter(
                models.Q(gcm_device__isnull=False) | models.Q(apns_device__isnull=False)
            )
        elif self.value() == "0":
            queryset = queryset.filter(
                gcm_device__isnull=True, apns_device__isnull=True
            )

        return queryset


@admin.register(DeviceWallet)
class DeviceWalletAdmin(admin.ModelAdmin):
    search_fields = [
        "gcm_device__device_id",
        "gcm_device__registration_id",
        "apns_device__device_id",
        "apns_device__registration_id",
        "wallet_hash",
        "last_active",
    ]

    list_display = [
        "__str__",
        "wallet_hash",
        "gcm_device",
        "apns_device",
        "last_active",
    ]

    list_filter = [
        HasNoDeviceFilter,
        "last_active",
    ]
