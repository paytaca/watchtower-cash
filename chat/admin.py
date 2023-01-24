from django.contrib import admin

from chat.models import ChatIdentity


class ChatIdentityAdmin(admin.ModelAdmin):
    search_fields = ['tokenid']
    actions = ['get_token_metadata']

    list_display = [
        'address',
        'email'
    ]


admin.site.register(ChatIdentity, ChatIdentityAdmin)
