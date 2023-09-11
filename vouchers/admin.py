from django.contrib import admin

from vouchers.models import *


class VaultAdmin(admin.ModelAdmin):
    search_fields = [
        'address',
        'token_address',
    ]
    list_display = [
        'merchant',
        'address',
        'token_address',
    ]


class VoucherAdmin(admin.ModelAdmin):
    search_fields = [
        'key_category',
        'lock_category',
    ]
    list_filter = [
        'claimed',
        'expired',
    ]
    list_display = [
        'vault',
        'key_category',
        'lock_category',
        'claimed',
        'expired',
        'duration_days',
        'date_created',
        'date_claimed',
    ]


admin.site.register(Vault, VaultAdmin)
admin.site.register(Voucher, VoucherAdmin)
