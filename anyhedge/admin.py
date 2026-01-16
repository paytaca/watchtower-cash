from django.contrib import admin
from django.contrib import messages

from anyhedge import models
from anyhedge.utils.funding import (
    attach_funding_tx_to_wallet_history_meta,
)
from anyhedge.utils.liquidity import resolve_liquidity_fee
from anyhedge.tasks import (
    check_new_oracle_price_messages,
    validate_contract_funding,
    update_contract_settlement_from_service,
    settle_contract_maturity,
)

# Register your models here.
@admin.register(models.Oracle)
class OracleAdmin(admin.ModelAdmin):
    search_fields = [
        "pubkey",
        "asset_name",
        "asset_currency",
    ]

    list_display = [
        "pubkey",
        "asset_name",
        "asset_currency",
        "asset_decimals",
        "active",
    ]

    actions = [
        "update_price",
    ]

    def update_price(self, request, queryset):
        for oracle in queryset:
            check_new_oracle_price_messages(oracle.pubkey)

class HedgePositionOfferCounterPartyInline(admin.StackedInline):
    model = models.HedgePositionOfferCounterParty
    extra = 0

@admin.register(models.HedgePositionOffer)
class HedgePositionOfferAdmin(admin.ModelAdmin):
    search_display = [
        "wallet_hash",
        "hedge_position__address",
    ]

    list_display = [
        "__str__",
        "wallet_hash",
        "position",
        "status",
        "satoshis",
        "duration_seconds",
        "high_liquidation_multiplier",
        "low_liquidation_multiplier",
        "hedge_position",
        "created_at",
        "expires_at",
    ]

    inlines = [
        HedgePositionOfferCounterPartyInline,
    ]


class HedgePositionMetadataInline(admin.StackedInline):
    model = models.HedgePositionMetadata
    extra = 0

class HedgeSettlementInline(admin.StackedInline):
    model = models.HedgeSettlement
    extra = 0

class HedgePositionFundingInline(admin.StackedInline):
    model = models.HedgePositionFunding
    extra = 0

class SettlementServiceInline(admin.StackedInline):
    model = models.SettlementService
    extra = 0

@admin.register(models.HedgePosition)
class HedgePositionAdmin(admin.ModelAdmin):
    search_fields = [
        "address",
        "short_wallet_hash",
        "long_wallet_hash",
        "short_address",
        "long_address",
    ]

    list_display = [
        "__str__",
        "start_timestamp",
        "maturity_timestamp",
        "satoshis",
        "funding_tx_hash",
        "position_offer",
    ]

    list_filter = [
        "funding_tx_hash_validated",
        "maturity_timestamp",
    ]

    actions = [
        'resolve_liquidity_fee',
        'validate_contract_funding',
        'attach_funding_tx_to_wallet_history_meta',
        'update_contract_settlement_from_service',
        'settle_contract_maturity',
    ]

    inlines = [
        HedgePositionMetadataInline,
        SettlementServiceInline,
        HedgePositionFundingInline,
        HedgeSettlementInline,
    ]

    def resolve_liquidity_fee(self, request, queryset):
        for hedge_position in queryset:
            result = resolve_liquidity_fee(hedge_position)
            messages.info(request, f"{result}")

    def validate_contract_funding(self, request, queryset):
        for hedge_position in queryset:
            result = validate_contract_funding(
                hedge_position.address,
            )
            messages.info(request, f"{result}")

    def attach_funding_tx_to_wallet_history_meta(self, request, queryset):
        for hedge_position in queryset:
            result = attach_funding_tx_to_wallet_history_meta(hedge_position)
            messages.info(request, f"{result}")

    def update_contract_settlement_from_service(self, request, queryset):
        for hedge_position in queryset:
            result = update_contract_settlement_from_service(hedge_position.address)
            messages.info(request, f"{result}")

    def settle_contract_maturity(self, request, queryset):
        for hedge_position in queryset:
            result = settle_contract_maturity(hedge_position.address)
            messages.info(request, f"{result}")
