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


class TreasuryContractKeyForm(forms.ModelForm):
    class Meta:
        model = models.TreasuryContractKey
        fields = "__all__"

    def _clean_wif(self, value):
        if value and is_valid_wif(value) and not value.startswith("bch-wif:"):
            value = encrypt_str(value)

        return value

    def clean_pubkey1_wif(self):
        return self._clean_wif(self.cleaned_data.get("pubkey1_wif"))

    def clean_pubkey2_wif(self):
        return self._clean_wif(self.cleaned_data.get("pubkey2_wif"))

    def clean_pubkey3_wif(self):
        return self._clean_wif(self.cleaned_data.get("pubkey3_wif"))

    def clean_pubkey4_wif(self):
        return self._clean_wif(self.cleaned_data.get("pubkey4_wif"))

    def clean_pubkey5_wif(self):
        return self._clean_wif(self.cleaned_data.get("pubkey5_wif"))
