from django import forms
from django.contrib import admin

from smartbch.models import (
    TransactionTransfer,
    Transaction
)

from smartbch.utils import transaction as transaction_utils

from .utils import BlockRangeFilter

class PullTransactionModelForm(forms.ModelForm):
    parse_transaction_transfers = forms.BooleanField(required=False)

    class Meta:
        model = Transaction
        fields=[
            "txid",
            "parse_transaction_transfers",
        ]

    def save_m2m(self, *args, **kwargs):
        pass

    def save(self, commit=True):
        if self.instance:
            txid = self.instance.txid
        else:
            txid = self.cleaned_data["txid"]
        parse_transaction_transfers = bool(self.cleaned_data["parse_transaction_transfers"])

        instance = transaction_utils.save_transaction(txid)
        if parse_transaction_transfers:
            instance = transaction_utils.save_transaction_transfers(
                txid,
                parse_block_timestamp=True,
            )

        return instance



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
        "processed_transfers",
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

    def get_form(self, request, obj=None, **kwargs):
        if not obj:
            return PullTransactionModelForm
        return super().get_form(request, obj=obj, **kwargs)
