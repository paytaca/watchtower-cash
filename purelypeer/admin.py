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


class CashdropNftPairAdmin(admin.ModelAdmin):
    search_fields = [
        'key_category',
        'lock_category',
    ]
    list_display = [
        'vault',
        'key_category',
        'lock_category',
    ]


admin.site.register(Vault, VaultAdmin)
admin.site.register(CashdropNftPair, CashdropNftPairAdmin)
