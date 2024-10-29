from django.contrib import admin
from django.contrib import messages

from stablehedge import models
from stablehedge.functions.treasury_contract import get_funding_wif_address
from stablehedge.js.runner import ScriptFunctions

from main import models as main_models
from main.utils.address_validator import is_token_address
from main.utils.address_converter import bch_address_converter
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
            token_address = bch_address_converter(obj.address, to_token_addr=True)
            addr_obj, _ = main_models.Address.objects.get_or_create(
                address=obj.address,
                token_address=token_address,
            )
            _, created = main_models.Subscription.objects.get_or_create(address=addr_obj)
            messages.info(request, f"{obj} | new: {created}")

    def update_utxos(self, request, queryset):
        for obj in queryset.all():
            get_bch_utxos.delay(obj.address)
            messages.info(request, f"Queued | {obj}")
    update_utxos.short_description = "Update UTXOS"


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
    ]
    list_filter = [
        "transaction_type",
        "status",
    ]


@admin.register(models.TreasuryContract)
class TreasuryContractAdmin(admin.ModelAdmin):
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
    ]

    actions = [
        "recompile",
        "subscribe",
        "subscribe_funding_wif",
        "update_utxos",
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

    # @admin.display(ordering='is_subscribed') # for django 5.0
    def is_subscribed(self, obj):
        return getattr(obj, "is_subscribed", None)
    is_subscribed.admin_order_field = "is_subscribed" # for django 3.0

    def subscribe(self, request, queryset):
        for obj in queryset.all():
            token_address = bch_address_converter(obj.address, to_token_addr=True)
            addr_obj, _ = main_models.Address.objects.get_or_create(
                address=obj.address,
                token_address=token_address,
            )
            _, created = main_models.Subscription.objects.get_or_create(address=addr_obj)
            messages.info(request, f"{obj} | new: {created}")

    def subscribe_funding_wif(self, request, queryset):
        for obj in queryset.all():
            address = get_funding_wif_address(obj.address)
            token_address = bch_address_converter(address, to_token_addr=True)
            addr_obj, _ = main_models.Address.objects.get_or_create(
                address=address,
                token_address=token_address,
            )
            _, created = main_models.Subscription.objects.get_or_create(address=addr_obj)
            messages.info(request, f"{obj} | new: {created}")

    def update_utxos(self, request, queryset):
        for obj in queryset.all():
            get_bch_utxos.delay(obj.address)
            messages.info(request, f"Queued | {obj}")
    update_utxos.short_description = "Update UTXOS"
