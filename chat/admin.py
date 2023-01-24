from django.contrib import admin

from chat.models import ChatIdentity, Conversation


class ChatIdentityAdmin(admin.ModelAdmin):
    search_fields = ['tokenid']
    actions = ['get_token_metadata']

    list_display = [
        'address',
        'email'
    ]


admin.site.register(ChatIdentity, ChatIdentityAdmin)


class ConversationAdmin(admin.ModelAdmin):
    search_fields = ['topic']
    list_display = [
        'from_address',
        'to_address',
        'topic',
        'date_created'
    ]


admin.site.register(Conversation, ConversationAdmin)
