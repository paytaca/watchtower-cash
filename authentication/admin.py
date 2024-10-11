from django.contrib import admin

from authentication.models import *

class AuthTokenAdmin(admin.ModelAdmin):
    list_display = ['wallet_hash', 'key_expires_at']
    search_fields = ['wallet_hash']

admin.site.register(AuthToken, AuthTokenAdmin)
