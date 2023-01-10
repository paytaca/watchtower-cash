from django.contrib import admin

from chat.models import PgpInfo


class PgpInfoAdmin(admin.ModelAdmin):
    search_fields = ['tokenid']
    actions = ['get_token_metadata']

    list_display = [
        'address',
        'email'
    ]


admin.site.register(PgpInfo, PgpInfoAdmin)
