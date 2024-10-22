from django.contrib import admin

from paymentvault.models import *


@admin.register(PaymentVault)
class PaymentVaultAdmin(admin.ModelAdmin):
    search_fields = [
        'address',
        'token_address',
        'user_pubkey',
    ]

    list_filter = [
        'merchant__name',
    ]

    list_display = [
        'user_pubkey',
        'merchant',
        'address',
        'token_address',
    ]