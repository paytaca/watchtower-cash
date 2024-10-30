from django import forms

from stablehedge import models
from stablehedge.utils.encryption import encrypt_str
from stablehedge.utils.wallet import is_valid_wif


class TreasuryContractForm(forms.ModelForm):
    class Meta:
        model = models.TreasuryContract
        fields = "__all__"

        help_texts = dict(
            encrypted_funding_wif="Value will be encrypted if wif is valid. " \
                    "Add prefix 'bch-wif:' to skip encryption. " \
                    "<br/>" \
                    "NOTE: Ensure there is no short proposal being created in progress. " \
                    "Sweep funding wif first before changing to prevent loss of funds. "
        )

    def clean_encrypted_funding_wif(self):
        value = self.cleaned_data.get("encrypted_funding_wif")

        if value and is_valid_wif(value) and not value.startswith("bch-wif:"):
            value = encrypt_str(value)

        return value
