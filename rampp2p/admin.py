from django.contrib import admin

# Register your models here.
from rampp2p.models import *


class AdAdmin(admin.ModelAdmin):
    list_display = [
        'trade_type',
        'crypto_currency',
        'fiat_currency',
        'owner',
        'is_public',
        'created_at'
    ]
    search_fields = [
        'fiat_currency',
        'owner'
    ]


admin.site.register(Ad, AdAdmin)


class FiatCurrencyAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'symbol',
        'created_at'
    ]
    search_fields = [
        'name',
        'symbol'
    ]

admin.site.register(FiatCurrency, FiatCurrencyAdmin)


class OrderAdmin(admin.ModelAdmin):
    list_display = [
        'ad_snapshot__trade_type',
        'crypto_amount',
        'owner',
        'created_at'
    ]

admin.site.register(Order, OrderAdmin)


admin.site.register(AdSnapshot)
admin.site.register(CryptoCurrency)
admin.site.register(Feedback)
admin.site.register(Status)
admin.site.register(PaymentType)
admin.site.register(PaymentMethod)
admin.site.register(Peer)
admin.site.register(MarketRate)
admin.site.register(Arbiter)
admin.site.register(Contract)
admin.site.register(Appeal)
admin.site.register(ContractMember)
admin.site.register(ReservedName)
admin.site.register(IdentifierFormat)
admin.site.register(OrderMember)