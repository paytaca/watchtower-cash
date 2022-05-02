from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.contrib import (
    admin,
    messages,
)
from smartbch.models import TokenContract

from smartbch.utils.contract import get_or_save_token_contract_metadata

class TokenContractAdminForm(forms.ModelForm):
    image = forms.FileField(required=False)

    class Meta:
        model = TokenContract
        fields = [
            "address",
            "name",
            "symbol",
            "image",
            "image_url",
            "image_url_source",
        ]

    def clean_image(self):
        file = self.cleaned_data["image"]
        if file is None:
            return file

        (file_type, file_ext) = file.content_type.split("/")
        if file_type != "image":
            raise ValidationError(f"Expected image file type got '{file.content_type}'")

        return file

    def clean_image_url(self):
        if "image_url" not in self.cleaned_data:
            return None

        if self.instance:
            self.instance.image_url_source = "admin"
        return self.cleaned_data["image_url"]


@admin.register(TokenContract)
class TokenContractAdmin(admin.ModelAdmin):    
    form = TokenContractAdminForm

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

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return []

        return ["address", "name", "symbol", "image_url_source"]

    # def has_change_permission(self, request, obj=None):
    #     if obj:
    #         return False
    #     return super().has_change_permission(request, obj=obj)

    def save_model(self, request, obj, form, change):
        if form.cleaned_data.get("image", None) is not None:
            file = form.cleaned_data["image"]
            (file_type, file_ext) = file.content_type.split("/")
            image_file_name = f"{obj.address}.{file_ext}"
            path = f"{settings.TOKEN_IMAGES_DIR}/{image_file_name}"
            image_server_base = 'https://images.watchtower.cash'
            image_url = f"{image_server_base}/{image_file_name}"
            obj.image_url = image_url
            obj.image_url_source = "admin"

            # form.cleaned_data["image"].read()

        return super().save_model(request, obj, form, change)

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
