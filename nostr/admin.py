from django.contrib import admin
from .models import NostrPubkey


@admin.register(NostrPubkey)
class NostrPubkeyAdmin(admin.ModelAdmin):
    list_display = (
        'pubkey_hex',
        'wallet_hash',
        'created_at',
        'last_active',
        'show_active_status',
    )
    list_filter = (
        'created_at',
        'last_active',
        'show_active_status',
    )
    search_fields = (
        'pubkey_hex',
        'wallet_hash',
    )
    readonly_fields = (
        'created_at',
        'last_active',
    )
    fieldsets = (
        (None, {
            'fields': (
                'pubkey_hex',
                'wallet_hash',
            ),
        }),
        ('Status', {
            'fields': (
                'last_active',
                'show_active_status',
            ),
        }),
        ('Metadata', {
            'fields': ('created_at',),
        }),
    )
