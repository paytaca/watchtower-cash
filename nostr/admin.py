from django.contrib import admin
from .models import NostrPubkey, NostrRoom, NostrBlockedContact, NostrBlockedGroup


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


@admin.register(NostrRoom)
class NostrRoomAdmin(admin.ModelAdmin):
    list_display = ('room_id', 'wallet_hash', 'type', 'name', 'archived', 'updated_at')
    list_filter = ('type', 'archived')
    search_fields = ('room_id', 'wallet_hash', 'name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(NostrBlockedContact)
class NostrBlockedContactAdmin(admin.ModelAdmin):
    list_display = ('wallet_hash', 'pub_key_hex', 'created_at')
    search_fields = ('wallet_hash', 'pub_key_hex')


@admin.register(NostrBlockedGroup)
class NostrBlockedGroupAdmin(admin.ModelAdmin):
    list_display = ('wallet_hash', 'room_id', 'created_at')
    search_fields = ('wallet_hash', 'room_id')
