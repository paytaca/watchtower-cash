from django.contrib import admin

from .models import Oracle

# Register your models here.
@admin.register(Oracle)
class OracleAdmin(admin.ModelAdmin):
    search_fields = [
        "pubkey",
        "asset_name",
        "asset_currency",
    ]

    list_display = [
        "pubkey",
        "asset_name",
        "asset_currency",
        "asset_decimals",
    ]
