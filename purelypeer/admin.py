from django.contrib import admin

from purelypeer.models import *


class VaultAdmin(admin.ModelAdmin):
    search_fields = [
        'address',
        'token_address',
    ]
    list_display = [
        'merchant',
        'address',
        'token_address',
    ]


admin.site.register(Vault, VaultAdmin)
