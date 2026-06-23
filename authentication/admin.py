from django.contrib import admin

from authentication.models import *

class AuthTokenAdmin(admin.ModelAdmin):
    list_display = ['wallet_hash', 'key_expires_at']
    search_fields = ['wallet_hash']
    actions = [
        'mark_as_expired'
    ]

    def mark_as_expired(self, request, queryset):
        for token in queryset:
            token.key_expires_at = timezone.now()
            token.save()

    mark_as_expired.short_description = "Mark as expired"


class ApiTokenAdmin(admin.ModelAdmin):
    list_display = [
        "uuid",
        "name",
        "scopes",
    ]

    list_filter = [
        "scopes",
    ]

    readonly_fields = [
        "uuid",
    ]


admin.site.register(AuthToken, AuthTokenAdmin)
admin.site.register(ApiToken, ApiTokenAdmin)
