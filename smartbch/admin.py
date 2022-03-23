from django.contrib import (
    admin,
    messages,
)
from django.db import models

from smartbch.models import (
    TokenContract,
    TransactionTransfer,
    Transaction,
)
from smartbch.utils.contract import get_or_save_token_contract_metadata

class TokenContractAdmin(admin.ModelAdmin):    
    search_fields = [
        "name",
        "symbol",
        "address",
    ]

    list_display = [
        "address",
        "name",
        "symbol",
        "token_type",
    ]
    actions = [
        'update_metadata',
    ]

    def has_change_permission(self, request, obj=None):
        if obj:
            return False
        return super().has_change_permission(request, obj=obj)

    def update_metadata(self, request, queryset):
        tokens_updated = []
        for token_contract in queryset.all():
            token_instance, _ = get_or_save_token_contract_metadata(token_contract.address)
            if token_instance:
                tokens_updated.append(token_instance.address)

        messages.add_message(
            request,
            messages.INFO,
            f"Updated {len(tokens_updated)} token metadata",
        )


class TransactionTransferAdmin(admin.ModelAdmin):
    search_fields = [
        "token_contract__name",
        "token_contract__symbol",
        "token_contract__address",
        "from_addr",
        "to_addr",
    ]

    list_display = [
        "get_short_txid",
        # "transaction__block__block_number",
        "from_addr",
        "to_addr",
        "amount",
        "unit_symbol",
    ]

    def get_short_txid(self, obj):
        if not obj or not obj.transaction:
            return
            
        if len(obj.transaction.txid) > 15:
            return obj.transaction.txid[:5] + "..." + obj.transaction.txid[-7:]
        else:
            return obj.transaction.txid

    get_short_txid.short_description = "Transaction"

    def has_change_permission(self, request, obj=None):
        return False


class TransactionTransferInline(admin.TabularInline):
    model = TransactionTransfer
    extra = 0


class TransactionAdmin(admin.ModelAdmin):
    list_select_related = [
        "block",
    ]

    list_display = [
        "txid",
        "from_addr",
        "to_addr",
    ]

    inlines = [
        TransactionTransferInline,
    ]

    def has_change_permission(self, request, obj=None):
        return False


admin.site.register(TokenContract, TokenContractAdmin)
admin.site.register(TransactionTransfer, TransactionTransferAdmin)
admin.site.register(Transaction, TransactionAdmin)
