import re
import web3
from django import forms
from django.urls import path
from django.shortcuts import render
from django.core.exceptions import ValidationError
from django.contrib import (
    admin,
    messages,
)
from django.db import models

from smartbch.models import TransactionTransfer
from smartbch.tasks import save_transactions_by_address_task__manual
from smartbch.utils import transaction as transaction_utils

from .utils import BlockRangeFilter, InputFilter


def _is_valid_address(address):
    if not web3.Web3.isAddress(address):
        raise ValidationError("invalid address")


class PullTransactionTransfersForm(forms.Form):
    start_block = forms.DecimalField(min_value=0, decimal_places=0)
    end_block = forms.DecimalField(min_value=0, decimal_places=0)
    address = forms.CharField(
        help_text="Pull transactions for address",
        validators = [
            _is_valid_address,
        ]
    )
    def clean(self):
        cleaned_data = super().clean()
        start_block = cleaned_data.get("start_block", None)
        end_block = cleaned_data.get("end_block", None)

        if start_block is not None and end_block is not None:
            if start_block > end_block:
                raise ValidationError("Start block must be less than or equal to end block")

            if end_block-start_block > 500:
                raise ValidationError("Block range too wide, must be less than 500")

        return cleaned_data

    def queue_task(self):
        data = self.cleaned_data
        return save_transactions_by_address_task__manual.delay(
            data["address"],
            from_block=data["start_block"],
            to_block=data["end_block"],
            block_partition=50,
        )


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
    change_list_template = 'admin/transaction_transfer_changelist.html'

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

    def get_urls(self, *args, **kwargs):
        urls = super().get_urls(*args, **kwargs)
        urls = [
            path('pull/', self.pull_tx_transfers_view, name="pull_transaction_transfers_form"),
        ] + urls

        return urls

    def pull_tx_transfers_view(self, request, *args, **kwargs):
        form = PullTransactionTransfersForm()
        if request.method == "POST":
            form = PullTransactionTransfersForm(request.POST)
            if form.is_valid():
                async_result = form.queue_task()
                messages.add_message(
                    request,
                    messages.INFO,
                    f"Queued pull transaction transfer task id: {async_result.task_id}"
                )
                return self.changelist_view(request)

        context = {
            "title": "Pull Transaction Transfers",
            "form": form,
        }

        return render(request, "admin/smartbch/pull_tx_transfers_form.html", context=context)

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

