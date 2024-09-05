from django.contrib import admin

from vouchers.models import *


@admin.register(PosDeviceVault)
class PosDeviceVaultAdmin(admin.ModelAdmin):
    search_fields = [
        'address',
        'token_address',
    ]
    list_display = [
        'pos_device',
        'address',
        'token_address',
    ]


@admin.register(MerchantVault)
class MerchantVaultAdmin(admin.ModelAdmin):
    search_fields = [
        'address',
        'token_address',
    ]
    list_display = [
        'merchant',
        'address',
        'token_address',
    ]


@admin.register(Voucher)
class VoucherAdmin(admin.ModelAdmin):
    search_fields = [
        'category',
    ]
    list_filter = [
        'claimed',
        'expired',
    ]
    list_display = [
        'vault',
        'category',
        'claimed',
        'expired',
        'duration_days',
        'date_created',
        'date_claimed',
    ]