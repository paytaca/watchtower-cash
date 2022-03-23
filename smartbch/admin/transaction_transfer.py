from django.contrib import admin
from django.db import models

from smartbch.models import TransactionTransfer

from .utils import BlockRangeFilter, InputFilter


class AssetTypeFilter(InputFilter):
    parameter_name = "asset"
    title = "Asset"

    def queryset(self, request, queryset):
        if self.value() is None:
            return

        return queryset.annotate(
            asset_name= models.Case(
                models.When(token_contract__isnull=True, then=models.Value("Bitcoin Cash")),
                default=models.F("token_contract__name"),
            ),
            asset_symbol= models.Case(
                models.When(token_contract__isnull=True, then=models.Value("BCH")),
                default=models.F("token_contract__symbol"),
            )
        ).filter(
            models.Q(asset_name__icontains=self.value()) | models.Q(asset_symbol__icontains=self.value())
        )


class BlockRangeFilter(BlockRangeFilter):
    def queryset(self, request, queryset):
        if not self.before_value() and not self.after_value():
            return None

        if self.after_value():
            queryset = queryset.filter(transaction__block__block_number__gte=self.after_value())

        if self.before_value():
            queryset = queryset.filter(transaction__block__block_number__lte=self.before_value())

        return queryset


@admin.register(TransactionTransfer)
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

    list_filter = [
        AssetTypeFilter,
        BlockRangeFilter,
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

