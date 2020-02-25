from django.contrib import admin
from main.models import Token, Transaction, SlpAddress, BlockHeight
from django.contrib.auth.models import User, Group

admin.site.site_header = 'SPLNotify'

class TokenAdmin(admin.ModelAdmin):
    list_display = [
        'tokenid',
        'confirmation_limit'
    ]

class BlockHeightAdmin(admin.ModelAdmin):
    list_display = [
        'number',
        'transactions_count',
        'created_datetime',
        'updated_datetime',
        'processed'
    ]

class TransactionAdmin(admin.ModelAdmin):
    list_display = [
        'txid',
        'amount',
        'source',
        'blockheight_number',
        'acknowledge',
        'created_datetime'
    ]

    def blockheight_number(self, obj):
        if obj.blockheight is not None:
            return obj.blockheight.number
        return '---' 

class SlpAddressAdmin(admin.ModelAdmin):
    list_display = [
        'token',
        'address'
    ]

admin.site.unregister(User)
admin.site.unregister(Group)
admin.site.register(Token, TokenAdmin)
admin.site.register(Transaction, TransactionAdmin)
admin.site.register(SlpAddress, SlpAddressAdmin)
admin.site.register(BlockHeight, BlockHeightAdmin)