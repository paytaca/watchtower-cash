from django.contrib import admin
from .models import NostrPubkeyDevice


@admin.register(NostrPubkeyDevice)
class NostrPubkeyDeviceAdmin(admin.ModelAdmin):
    list_display = (
        'pubkey_hex',
        'wallet_hash',
        'multi_wallet_index',
        'created_at',
        'last_active',
    )
    list_filter = (
        'created_at',
        'last_active',
    )
    search_fields = (
        'pubkey_hex',
        'wallet_hash',
    )
    readonly_fields = (
        'created_at',
        'last_active',
    )
