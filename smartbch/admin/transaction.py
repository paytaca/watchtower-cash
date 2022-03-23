from django.contrib import admin

from smartbch.models import (
    TransactionTransfer,
    Transaction
)

from .utils import BlockRangeFilter


class BlockRangeFilter(BlockRangeFilter):
    def queryset(self, request, queryset):
        if not self.before_value() and not self.after_value():
            return None

        if self.after_value():
            queryset = queryset.filter(block__block_number__gte=self.after_value())

        if self.before_value():
            queryset = queryset.filter(block__block_number__lte=self.before_value())

        return queryset


class TransactionTransferInline(admin.TabularInline):
    model = TransactionTransfer
    extra = 0


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = [
        "txid",
        "block_number",
        "from_addr",
        "to_addr",
    ]

    inlines = [
        TransactionTransferInline,
    ]

    list_filter = [
        BlockRangeFilter,
    ]

    def has_change_permission(self, request, obj=None):
        return False

    def block_number(self, obj):
        return obj.block_number

    block_number.admin_order_field = 'block__block_number'
