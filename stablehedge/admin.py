from django.contrib import admin
from django.contrib import messages

from stablehedge import models
from stablehedge.js.runner import ScriptFunctions


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
    ]

    list_display = [
        "address",
        "price_oracle_pubkey",
        "fiat_token",
    ]

    actions = [
        "recompile",
    ]

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
        "pubkey1",
        "pubkey2",
        "pubkey3",
        "pubkey4",
        "pubkey5",
    ]

    list_display = [
        "__str__",
        "auth_token_id",
    ]

    actions = [
        "recompile",
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

