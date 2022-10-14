from django.contrib import admin

from .models import PosDevice

# Register your models here.

@admin.register(PosDevice)
class PosDeviceAdmin(admin.ModelAdmin):
    search_fields = [
        "wallet_hash",
        "name",
    ]

    list_display = [
        "wallet_hash",
        "posid",
        "name",
    ]
