from django.contrib import admin
from django.contrib import messages

from stablehedge.apps import LOGGER
from stablehedge import models
from stablehedge import forms
from stablehedge.functions.anyhedge import StablehedgeException, AnyhedgeException
from stablehedge.functions.treasury_contract import (
    get_funding_wif_address,
    sweep_funding_wif,
    get_spendable_sats,
)
from stablehedge.functions.redemption_contract import get_24hr_volume_data
from stablehedge.functions.transaction import update_redemption_contract_tx_trade_size
from stablehedge.js.runner import ScriptFunctions
from stablehedge.utils.wallet import subscribe_address
from stablehedge.tasks import check_and_short_funds

from main.tasks import get_bch_utxos


# Register your models here.
@admin.register(models.FiatToken)
class FiatTokenAdmin(admin.ModelAdmin):
    search_fields = [
        "category",
        "currency",
    ]

    list_display = [
        "__str__",
        "currency",
        "decimals",
    ]


@admin.register(models.RedemptionContract)
class RedemptionContractAdmin(admin.ModelAdmin):
    form = forms.RedemptionContractForm

    search_fields = [
        "address",
        "auth_token_id",
        "price_oracle_pubkey",
        "treasury_contract__address",
    ]

    list_display = [
        "__str__",
        "price_oracle_pubkey",
        "fiat_token",
        "treasury_contract_address",
        "is_subscribed",
    ]

    actions = [
        "recompile",
        "subscribe",
        "update_utxos",
        "recalculate_24hr_volume",
    ]

    def get_queryset(self, request):
        return super().get_queryset(request) \
            .select_related("treasury_contract") \
            .annotate_is_subscribed()

    # @admin.display(ordering='is_subscribed') # for django 5.0
    def is_subscribed(self, obj):
        return getattr(obj, "is_subscribed", None)
    is_subscribed.admin_order_field = "is_subscribed" # for django 3.0

    def recompile(self, request, queryset):
        for obj in queryset.all():
            network = "chipnet" if obj.address.startswith("bchtest") else "mainnet"
            compile_data = ScriptFunctions.compileRedemptionContract(obj.contract_opts)

            if obj.address != compile_data["address"]:
                messages.info(request, f"RedemptionContract({obj.address}) -> {compile_data['address']}")
                obj.address = compile_data["address"]
                obj.save()
            else:
                messages.info(request, f"RedemptionContract({obj.address})")

    recompile.short_description = "Recompile address"

    def subscribe(self, request, queryset):
        for obj in queryset.all():
            created = subscribe_address(obj.address)
            messages.info(request, f"{obj} | new: {created}")

    def update_utxos(self, request, queryset):
        for obj in queryset.all():
            get_bch_utxos.delay(obj.address)
            messages.info(request, f"Queued | {obj}")
    update_utxos.short_description = "Update UTXOS"

    def recalculate_24hr_volume(self, request, queryset):
        for obj in queryset.all():
            result = get_24hr_volume_data(obj.address, force=True)
            messages.info(request, f"{obj.address} | {result}")
    recalculate_24hr_volume.short_description = "Recalculate 24 volume data"

@admin.register(models.RedemptionContractTransaction)
class RedemptionContractTransactionAdmin(admin.ModelAdmin):
    search_fields = [
        "txid",
    ]

    list_display = [
        "__str__",
        "redemption_contract",
        "transaction_type",
        "status",
        "trade_size_in_satoshis",
        "trade_size_in_token_units",
    ]
    list_filter = [
        "transaction_type",
        "status",
    ]

    actions = [
        "recalculate_trade_size",
    ]

    def recalculate_trade_size(self, request, queryset):
        count = 0
        for obj in queryset:

            updated_obj = update_redemption_contract_tx_trade_size(obj)
            count += 1
            if count < 10:
                messages.info(request, f"{updated_obj} | satoshis={updated_obj.trade_size_in_satoshis} | tokens={updated_obj.trade_size_in_token_units}")

        messages.info(request, f"Updated count: {count}")
    recalculate_trade_size.short_description = "Recalculate trade size"

class TreasuryContractKeyInline(admin.StackedInline):
    model = models.TreasuryContractKey
    extra = 0
    form = forms.TreasuryContractKeyForm

class TreasuryContractShortPositionRuleInline(admin.StackedInline):
    model = models.TreasuryContractShortPositionRule
    extra = 0

@admin.register(models.TreasuryContract)
class TreasuryContractAdmin(admin.ModelAdmin):
    form = forms.TreasuryContractForm

    inlines = [
        TreasuryContractKeyInline,
        TreasuryContractShortPositionRuleInline,
    ]

    search_fields = [
        "auth_token_id",
        "redemption_contract__address",
        "pubkey1",
        "pubkey2",
        "pubkey3",
        "pubkey4",
        "pubkey5",
    ]

    list_display = [
        "__str__",
        "redemption_contract",
        "auth_token_id",
        "is_subscribed",
        "get_spendable_satoshis",
    ]

    actions = [
        "recompile",
        "subscribe",
        "subscribe_funding_wif",
        "update_utxos",
        "sweep_funding_wif",
        "short_funds",
    ]

    def recompile(self, request, queryset):
        for obj in queryset.all():
            compile_data = ScriptFunctions.compileTreasuryContract(obj.contract_opts)

            if obj.address != compile_data["address"]:
                messages.info(request, f"TreasuryContract({obj.address}) -> {compile_data['address']}")
                obj.address = compile_data["address"]
                obj.save()
            else:
                messages.info(request, f"TreasuryContract({obj.address})")

    recompile.short_description = "Recompile address"

    def get_queryset(self, request):
        return super().get_queryset(request) \
            .select_related("redemption_contract") \
            .annotate_is_subscribed()

    def get_spendable_satoshis(self, obj):
        balance_data = get_spendable_sats(obj.address)
        spendable_sats = None
        if isinstance(balance_data, dict):
            spendable_sats = balance_data.get("spendable")
        return spendable_sats

    get_spendable_satoshis.short_description = 'Spendable satoshis'

    # @admin.display(ordering='is_subscribed') # for django 5.0
    def is_subscribed(self, obj):
        return getattr(obj, "is_subscribed", None)
    is_subscribed.admin_order_field = "is_subscribed" # for django 3.0

    def subscribe(self, request, queryset):
        for obj in queryset.all():
            created = subscribe_address(obj.address)
            messages.info(request, f"{obj} | new: {created}")

    def subscribe_funding_wif(self, request, queryset):
        for obj in queryset.all():
            address = get_funding_wif_address(obj.address)
            created = subscribe_address(address)
            messages.info(request, f"{obj} | {address} | new: {created}")

    def update_utxos(self, request, queryset):
        for obj in queryset.all():
            get_bch_utxos.delay(obj.address)
            messages.info(request, f"Queued | {obj}")
    update_utxos.short_description = "Update UTXOS"

    def sweep_funding_wif(self, request, queryset):
        for obj in queryset.all():
            try:
                txid = sweep_funding_wif(obj.address)
                messages.info(request, f"Sweep | {obj} | {txid}")
            except Exception as exception:
                messages.error(request, f"Sweep | {obj} | {exception}")
                LOGGER.exception(exception)

    def short_funds(self, request, queryset):
        if queryset.count() > 1:
            messages.error(request, f"Select only 1")
            return

        obj = queryset.first()
        try:
            result = check_and_short_funds(obj.address, min_sats=0)
            messages.info(request, f"{result}")
        except (StablehedgeException, AnyhedgeException) as exception:
            messages.error(f"Error: {exception}")
