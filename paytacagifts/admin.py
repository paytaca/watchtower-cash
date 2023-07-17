from paytacagifts.models import Wallet, Campaign, Gift, Claim
from django.contrib import admin


class WalletAdmin(admin.ModelAdmin):
    list_display = ['id', 'date_created', 'wallet_hash']


class CampaignAdmin(admin.ModelAdmin):
    list_display = ['id','date_created','name','limit_per_wallet','wallet']


class GiftAdmin(admin.ModelAdmin):
    list_display = ['id', 'date_created', 'gift_code_hash', 'address', 'amount', 'share', 'date_funded', 'date_claimed', 'wallet']


class ClaimAdmin(admin.ModelAdmin):
    list_display = ['id', 'date_created', 'amount', 'wallet']


admin.site.register(Wallet, WalletAdmin)
admin.site.register(Campaign, CampaignAdmin)
admin.site.register(Gift, GiftAdmin)
admin.site.register(Claim, ClaimAdmin)