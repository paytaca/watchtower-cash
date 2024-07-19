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
        'id',
        'ad_snapshot__trade_type',
        'crypto_amount',
        'owner',
        'created_at'
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("ad_snapshot")

    def ad_snapshot__trade_type(self, obj):
        if obj.ad_snapshot:
            return obj.ad_snapshot.trade_type
        return None


admin.site.register(Order, OrderAdmin)

class MarketRateAdmin(admin.ModelAdmin):
    list_display = [
        'currency',
        'price',
        'modified_at'
    ]
    search_fields = [
        'currency'
    ]

admin.site.register(MarketRate, MarketRateAdmin)

class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = [
        'payment_type',    
        'owner'
    ]

admin.site.register(PaymentMethod, PaymentMethodAdmin)

class ArbiterAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'inactive_until',
        'is_disabled'
    ]

admin.site.register(Arbiter, ArbiterAdmin)

class ContractAdmin(admin.ModelAdmin):
    list_display = [
        'order',
        'address',
        'version',
        'created_at'
    ]
    search_fields = [
        'address',
        'order',
        'version'
    ]

admin.site.register(Contract, ContractAdmin)

class PaymentTypeAdmin(admin.ModelAdmin):
    list_display = [
        'full_name',
        'short_name',
        'is_disabled'
    ]

admin.site.register(PaymentType, PaymentTypeAdmin)

class PeerAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'address',
        'is_disabled'
    ]
    search_fields = [
        'name',
        'address'
    ]

admin.site.register(Peer, PeerAdmin)

class StatusAdmin(admin.ModelAdmin):
    list_display = [
        'order',
        'status',
        'created_at'
    ]
    search_fields = [
        'order',
        'status'
    ]

admin.site.register(Status, StatusAdmin)

class FeedbackAdmin(admin.ModelAdmin):
    list_display = [
        'order',
        'from_peer',
        'to_peer',
        'rating',
        'comment',
        'created_at'
    ]
    search_fields = [
        'order',
        'from_peer',
        'to_peer',
        'rating'
    ]

admin.site.register(Feedback, FeedbackAdmin)

class AppealAdmin(admin.ModelAdmin):
    list_display = [
        'type',
        'order',
        'owner',
        'created_at',
        'resolved_at'
    ]
    search_fields = [
        'order',
        'owner'
    ]

admin.site.register(Appeal, AppealAdmin)

class ContractMemberAdmin(admin.ModelAdmin):
    list_display = [
        'contract',
        'member_type',
        'address',
    ]

admin.site.register(ContractMember, ContractMemberAdmin)

class AdSnapshotAdmin(admin.ModelAdmin):
    list_display = [
        'ad',
        'trade_type',
        'created_at'
    ]

admin.site.register(AdSnapshot, AdSnapshotAdmin)

class TransactionAdmin(admin.ModelAdmin):
    list_display = [
        'contract',
        'txid',
        'action',
        'valid',
        'created_at'
    ]
    search_fields = [
        'txid'
    ]
admin.site.register(Transaction, TransactionAdmin)

admin.site.register(CryptoCurrency)
admin.site.register(ReservedName)
admin.site.register(IdentifierFormat)
admin.site.register(OrderMember)
admin.site.register(OrderPaymentMethod)

class PaymentTypeFieldAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'payment_type',
        'fieldname',
        'required'
    ]
    search_fields = [
        'fieldname'
    ]
admin.site.register(PaymentTypeField, PaymentTypeFieldAdmin)

class PaymentMethodFieldAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'payment_method_name',
        'field_reference_name',
        'value',
        'created_at',
        'modified_at'
    ]
    search_fields = [
        'value'
    ]
    
    def payment_method_name(self, obj):        
        name = obj.payment_method.payment_type.full_name
        if name:
            name = obj.payment_method.payment_type.short_name
        return name
        
    def field_reference_name(self, obj):
        return obj.field_reference.fieldname
    
admin.site.register(PaymentMethodField, PaymentMethodFieldAdmin)