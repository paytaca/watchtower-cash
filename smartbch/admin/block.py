from django import forms
from django.contrib import admin

from smartbch.models import (
    Block,
    Transaction,
)
from smartbch.utils import block as block_utils
from smartbch.utils import transaction as transaction_utils

from .utils import BlockRangeFilter

class BlockRangeFilter(BlockRangeFilter):
    def queryset(self, request, queryset):
        if not self.before_value() and not self.after_value():
            return None

        if self.after_value():
            queryset = queryset.filter(block_number__gte=self.after_value())

        if self.before_value():
            queryset = queryset.filter(block_number__lte=self.before_value())

        return queryset


class TransactionInline(admin.StackedInline):
    model = Transaction
    extra = 0

    can_delete = False
    readonly_fields = (
        "txid",
        "from_addr",
        "to_addr",
        "value",
        "data",
        "gas",
        "gas_price",
        "is_mined",
        "status",
        "processed_transfers",
    )


class BlockModelAdminForm(forms.ModelForm):
    save_all_transactions = forms.BooleanField(
        help_text="If to include transactions that don't have addresses subscribed",
        required=False,
    )

    save_transfers = forms.BooleanField(
        help_text="If to save transaction transfers of transactions",
        required=False,
    )

    class Meta:
        model = Block
        fields = [
            "block_number",
            "processed",
            "timestamp",
            "transactions_count",
            "save_all_transactions",
            "save_transfers",
        ]

    def save_m2m(self, *args, **kwargs):
        pass

    def save(self, commit=True):
        if self.instance:
            block_number = self.instance.block_number
        else:
            block_number = self.cleaned_data["block_number"]

        save_all_transactions = bool(self.cleaned_data["save_all_transactions"])
        save_transfers = bool(self.cleaned_data["save_transfers"])

        instance = block_utils.parse_block(
            int(block_number),
            save_transactions=True,
            save_all_transactions=save_all_transactions,
        )

        if save_transfers:
            for tx_obj in instance.transactions.all():
                transaction_utils.save_transaction_transfers(tx_obj.txid)

        return instance



@admin.register(Block)
class BlockAdmin(admin.ModelAdmin):
    form = BlockModelAdminForm
    search_fields = [
        "block_number",
    ]

    list_display = [
        "block_number",
        "timestamp",
        "processed",
        "transactions_count",
        "id",
    ]

    inlines = [
        TransactionInline,
    ]

    list_filter = [
        BlockRangeFilter,
    ]

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + (
                "block_number",
            )
        else:
            return self.readonly_fields + (
                "timestamp",
                "transactions_count",
                "processed",
            )

