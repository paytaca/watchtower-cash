from django.contrib import admin
from .models import NostrPubkey


@admin.register(NostrPubkey)
class NostrPubkeyAdmin(admin.ModelAdmin):
    list_display = (
        'pubkey_hex',
        'wallet_hash',
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
