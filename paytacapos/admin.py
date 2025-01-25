from django.contrib import admin
from dynamic_raw_id.admin import DynamicRawIDMixin
from .models import *

from main.models import (
    Wallet,
    WalletHistory
)

def IsNullListFilter(parameter_name):
    """
        https://docs.djangoproject.com/en/dev/ref/contrib/admin/filters/#modeladmin-list-filters
        https://www.geeksforgeeks.org/create-classes-dynamically-in-python/
    """
    parent_class = (admin.SimpleListFilter, )
    def lookups(self, request, model_admin):
        return [
            ("true", 'Yes'),
            ("false", 'No'),
        ]

    def queryset(self, request, queryset):
        raw_value = self.value()
        value = None
        if str(raw_value).lower() == "false":
            value = False
        if str(raw_value).lower() == "true":
            value = True

        kwargs = {}
        if value == True:
            kwargs[f"{parameter_name}__isnull"] = True
        elif value == False:
            kwargs[f"{parameter_name}__isnull"] = False

        return queryset.filter(**kwargs)

    return type(f"IsNullListFilter({parameter_name})", parent_class, {
        "title": f"{parameter_name.capitalize()} is null",
        "parameter_name": parameter_name,
        "lookups": lookups,
        "queryset": queryset,
    })

# Register your models here.

@admin.register(PosDevice)
class PosDeviceAdmin(DynamicRawIDMixin, admin.ModelAdmin):
    search_fields = [
        "wallet_hash",
        "name",
        "merchant__name",
    ]

    dynamic_raw_id_fields = [
        'latest_transaction'
    ]

    list_display = [
        "wallet_hash",
        "posid",
        "name",
        "merchant",
        "branch",
    ]

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    search_fields = [
        'name',
    ]

    list_display = [
        'name',
    ]


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = [
        'merchant',
        'rating',
        'date',
    ]


@admin.register(Merchant)
class MerchantAdmin(admin.ModelAdmin):
    list_filter = [
        'category__name',
    ]
    search_fields = [
        "wallet_hash",
        "name",
        "category__name",
    ]

    list_display = [
        "name",
        "merchant_location",
        "verified",
        "active",
        "incoming_txs",
        "outgoing_txs",
        "last_transaction"
    ]

    actions = [
        "sync_main_branch_location",
    ]
    
    def merchant_location(self, obj):
        _location = ''
        if obj.location:
            if obj.location.city:
                _location = obj.location.city
            else:
                if obj.location.town:
                    _location = f'{obj.location.town}, {obj.location.province}'
            if obj.location.country:
                if _location:
                    _location += f', {obj.location.country}'
                else:
                    _location = obj.location.country
        return _location
    
    def incoming_txs(self, obj):
        wallet = Wallet.objects.get(wallet_hash=obj.wallet_hash)
        in_history = WalletHistory.objects.filter(wallet=wallet, record_type='incoming')
        return in_history.count()

    def outgoing_txs(self, obj):
        wallet = Wallet.objects.get(wallet_hash=obj.wallet_hash)
        out_history = WalletHistory.objects.filter(wallet=wallet, record_type='outgoing')
        return out_history.count()

    def last_transaction(self, obj):
        return obj.last_transaction_date

    def sync_main_branch_location(self, request, queryset):
        for merchant in queryset:
            merchant.location.sync_main_branch_location()
    sync_main_branch_location.short_description = "Sync location to main branch location"


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    search_fields = [
        "merchant__wallet_hash",
        "merchant__name",
        "name",
    ]

    list_display = [
        "name",
        "merchant",
    ]

    actions = [
        "sync_merchant_location",
    ]

    def sync_merchant_location(self, request, queryset):
        for branch in queryset:
            branch.sync_location_to_merchant()
    sync_merchant_location.short_description = "Sync location to merchant location"

@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    search_fields = [
        "merchant__wallet_hash",
        "merchant__name",
        "branch__name",
    ]

    list_filter = [
        IsNullListFilter("merchant"),
        IsNullListFilter("branch"),
    ]

    list_display = [
        "__str__",
        "merchant",
        "branch",
    ]
    