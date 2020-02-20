from django.contrib import admin
from main.models import BchToken, Transaction, SlpAddress
from django.contrib.auth.models import User, Group

class BchTokenAdmin(admin.ModelAdmin):
    list_display = [
        'tokenid',
        'confirmation_limit'
    ]
    
    
    
class TransactionAdmin(admin.ModelAdmin):
    list_display = [
        'txid',
    ]
    

class SlpAddressAdmin(admin.ModelAdmin):
    list_display = [
        'token',
        'address'
    ]

admin.site.unregister(User)
admin.site.unregister(Group)
admin.site.register(BchToken, BchTokenAdmin)
admin.site.register(Transaction, TransactionAdmin)
admin.site.register(SlpAddress, SlpAddressAdmin)