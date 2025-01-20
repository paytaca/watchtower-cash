from django.contrib import admin
from rampp2p.models import *
from rampp2p.forms import *
from rampp2p.slackbot.send import MessageBase
from dynamic_raw_id.admin import DynamicRawIDMixin

# Register your models here.

@admin.register(FeatureControl)
class FeatureControlAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_enabled']
    actions = ['enable', 'disable']

    def enable(self, request, queryset):
        for feature in queryset:
            feature.is_enabled = True
            feature.save()

    enable.short_description = "Enable selected features"

    def disable(self, request, queryset):
        for feature in queryset:
            feature.is_enabled = False
            feature.save()

    disable.short_description = "Disable selected features"

@admin.register(TradeFee)
class TradeFeeAdmin(admin.ModelAdmin):
    form = TradeFeeForm
    list_display = ['category', 'type', 'fixed_value', 'floating_value', 'updated_at']

    def has_add_permission(self, request):
        arbitration_fee_exists = TradeFee.objects.filter(category=TradeFee.FeeCategory.ARBITRATION).exists()
        service_fee_exists = TradeFee.objects.filter(category=TradeFee.FeeCategory.SERVICE).exists()
        return not (arbitration_fee_exists and service_fee_exists)
    
    def has_delete_permission(self, request, obj = None):
        return False

@admin.register(Ad)
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

@admin.register(FiatCurrency)
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

@admin.register(CryptoCurrency)
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

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'ad_snapshot__trade_type',
        'trade_amount',
        'owner',
        'created_at'
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("ad_snapshot")

    def ad_snapshot__trade_type(self, obj):
        if obj.ad_snapshot:
            return obj.ad_snapshot.trade_type
        return None

@admin.register(MarketRate)
class MarketRateAdmin(admin.ModelAdmin):
    list_display = [
        'currency',
        'price',
        'modified_at'
    ]
    search_fields = [
        'currency'
    ]

@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = [
        'payment_type',    
        'owner'
    ]

@admin.register(Arbiter)
class ArbiterAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'inactive_until',
        'is_disabled'
    ]

@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    readonly_fields = ['order', 'address', 'version', 'contract_fee', 'arbitration_fee', 'service_fee']
    list_display = [
        'order',
        'address',
        'version',
        'created_at'
    ]
    search_fields = [
        'address',
        'order__id',
        'version'
    ]

@admin.register(PaymentType)
class PaymentTypeAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'full_name',
        'short_name',
        'is_disabled'
    ]

@admin.register(Peer)
class PeerAdmin(admin.ModelAdmin):
    list_display = ['name', 'address', 'is_disabled']
    search_fields = ['name', 'address', 'wallet_hash']

@admin.register(Status)
class StatusAdmin(DynamicRawIDMixin, admin.ModelAdmin):
    list_display = ['order', 'status', 'created_at']
    search_fields = ['order__id', 'status']
    dynamic_raw_id_fields = ['order']

@admin.register(Feedback)
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
        'order__id',
        'from_peer__name',
        'to_peer__name',
        'rating'
    ]

@admin.register(Appeal)
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

@admin.register(ContractMember)
class ContractMemberAdmin(admin.ModelAdmin):
    list_display = [
        'contract',
        'member_type',
        'address',
    ]

@admin.register(AdSnapshot)
class AdSnapshotAdmin(admin.ModelAdmin):
    list_display = [
        'ad',
        'trade_type',
        'created_at'
    ]

@admin.register(Transaction)
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

@admin.register(OrderMember)
class OrderMemberAdmin(admin.ModelAdmin):
    list_display = ['order', 'type', 'name']
    search_fields = ['order__id', 'type']

@admin.register(OrderPayment)
class OrderPaymentAdmin(admin.ModelAdmin):
    list_display = ['id', 'order', 'payment_type', 'payment_method']
    search_fields = ['id', 'order__id', 'payment_type__short_name', 'payment_type__full_name', 'payment_method__id']

@admin.register(PaymentTypeField)
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

@admin.register(PaymentMethodField)
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
    
@admin.register(AppVersion)
class AppVersionAdmin(admin.ModelAdmin):
    list_display = ['latest_version', 'min_required_version', 'platform', 'release_date']
    fields = ['platform', 'latest_version', 'min_required_version', 'release_date', 'notes']

@admin.register(SlackMessageLog)
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

admin.site.register(ImageUpload)
admin.site.register(OrderPaymentAttachment)
admin.site.register(ReservedName)
admin.site.register(IdentifierFormat)
admin.site.register(DynamicPaymentTypeField)
