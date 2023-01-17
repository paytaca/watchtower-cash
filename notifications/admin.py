from django.contrib import admin

from .models import DeviceWallet

# Register your models here.
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
