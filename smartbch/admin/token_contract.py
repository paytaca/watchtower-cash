from django.contrib import (
    admin,
    messages,
)
from smartbch.models import TokenContract

from smartbch.utils.contract import get_or_save_token_contract_metadata

@admin.register(TokenContract)
class TokenContractAdmin(admin.ModelAdmin):    
    search_fields = [
        "name",
        "symbol",
        "address",
    ]

    list_display = [
        "address",
        "name",
        "symbol",
        "token_type",
    ]
    actions = [
        'update_metadata',
    ]

    def has_change_permission(self, request, obj=None):
        if obj:
            return False
        return super().has_change_permission(request, obj=obj)

    def update_metadata(self, request, queryset):
        tokens_updated = []
        for token_contract in queryset.all():
            token_instance, _ = get_or_save_token_contract_metadata(token_contract.address)
            if token_instance:
                tokens_updated.append(token_instance.address)

        messages.add_message(
            request,
            messages.INFO,
            f"Updated {len(tokens_updated)} token metadata",
        )
