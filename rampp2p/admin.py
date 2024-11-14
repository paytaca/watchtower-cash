from django.contrib import admin
from rampp2p.models import *
from rampp2p.forms import *

# Register your models here.

class ServiceFeeAdmin(admin.ModelAdmin):
    form = ServiceFeeForm
    list_display = ['type', 'fixed_value', 'floating_value', 'updated_at']

    def has_add_permission(self, request):
        return not ServiceFee.objects.exists()
    
    def has_delete_permission(self, request, obj = None):
        return False
    
admin.site.register(ServiceFee, ServiceFeeAdmin)

class AdAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'price_type',
        'trade_type',
        'crypto_currency',
        'fiat_currency',
        'owner',
        'is_public',
        'deleted_at'
    ]
    search_fields = [
        'id',
        'price_type',
        'trade_type',
        'fiat_currency__symbol',
        'owner__name'
    ]
    actions = [
        'soft_delete', 'mark_public', 'mark_private'
    ]

    def soft_delete(self, request, queryset):
        for ad in queryset:
            ad.deleted_at = timezone.now()
            ad.save()

    soft_delete.short_description = "Soft delete selected ads"

    def mark_public(self, request, queryset):
        for ad in queryset:
            ad.is_public = True
            ad.save()
    
    mark_public.short_description = "Mark selected ads as public"

    def mark_private(self, request, queryset):
        for ad in queryset:
            ad.is_public = False
            ad.save()
    
    mark_private.short_description = "Mark selected ads as private"


admin.site.register(Ad, AdAdmin)

class FiatCurrencyAdmin(admin.ModelAdmin):
    form = FiatCurrencyForm

    def save_model(self, request, obj, form, change):
        obj.cashin_presets = form.cleaned_data['cashin_presets']
        super().save_model(request, obj, form, change)

    def cashin_presets_display(self, obj):
        presets = obj.get_cashin_presets()
        if presets:
            return ', '.join(map(str, presets))
        return None
        
    cashin_presets_display.short_description = 'Cash In Presets'

    list_display = ['name', 'symbol', 'cashin_presets_display']
    search_fields = ['name', 'symbol']

admin.site.register(FiatCurrency, FiatCurrencyAdmin)

class CryptoCurrencyAdmin(admin.ModelAdmin):
    form = CryptoCurrencyForm

    def save_model(self, request, obj, form, change):
        obj.cashin_presets = form.cleaned_data['cashin_presets']
        super().save_model(request, obj, form, change)

    def cashin_presets_display(self, obj):
        presets = obj.get_cashin_presets()
        if presets:
            return ', '.join(map(str, presets))
        return None
        
    cashin_presets_display.short_description = 'Cash In Presets'

    list_display = ['name', 'symbol', 'cashin_presets_display']
    search_fields = ['name', 'symbol']

admin.site.register(CryptoCurrency, CryptoCurrencyAdmin)

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
        'id',
        'full_name',
        'short_name',
        'is_disabled'
    ]

admin.site.register(PaymentType, PaymentTypeAdmin)

class PeerAdmin(admin.ModelAdmin):
    list_display = ['name', 'address', 'is_disabled']
    search_fields = ['name', 'address']

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
        'id',
        'type',
        'order',
        'owner',
        'created_at',
        'resolved_at'
    ]
    search_fields = ['id', 'order__id', 'owner__name']

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

admin.site.register(ReservedName)
admin.site.register(IdentifierFormat)

class OrderMemberAdmin(admin.ModelAdmin):
    list_display = ['order', 'type', 'name']
    search_fields = ['order__id', 'type']

admin.site.register(OrderMember, OrderMemberAdmin)

class OrderPaymentAdmin(admin.ModelAdmin):
    list_display = ['id', 'order', 'payment_type', 'payment_method']
    search_fields = ['id', 'order__id', 'payment_type__short_name', 'payment_type__full_name', 'payment_method__id']

admin.site.register(OrderPayment, OrderPaymentAdmin)
admin.site.register(DynamicPaymentTypeField)

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
admin.site.register(ImageUpload)
admin.site.register(OrderPaymentAttachment)

class AppVersionAdmin(admin.ModelAdmin):
    list_display = ['platform', 'latest_version', 'min_required_version', 'release_date']
    fields = ['platform', 'latest_version', 'min_required_version', 'notes']

admin.site.register(AppVersion, AppVersionAdmin)

from rampp2p.slackbot.send import MessageBase
class SlackMessageLogAdmin(admin.ModelAdmin):
    search_fields = [
        "topic",
        "object_id",
        "channel",
        "ts",
    ]

    list_display = [
        "__str__",
        "topic",
        "object_id",
        "channel",
        "ts",
        "thread_ts",
        "metadata",
        "deleted_at",
    ]

    actions = [
        "delete_in_slack",
    ]

    def delete_in_slack(self, request, queryset):
        for msg in queryset:
            MessageBase.delete_message(
                msg.channel,
                str(msg.ts),
                update_db=True,
            )

    delete_in_slack.short_description = "Delete selected messages in slack"

admin.site.register(SlackMessageLog, SlackMessageLogAdmin)