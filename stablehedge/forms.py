from django import forms
from django.conf import settings

from stablehedge.apps import LOGGER
from stablehedge import models
from stablehedge.js.runner import ScriptFunctions
from stablehedge.utils.encryption import encrypt_str
from stablehedge.utils.wallet import is_valid_wif


class RedemptionContractForm(forms.ModelForm):
    address = forms.CharField(
        max_length=100, required=False,
        widget=forms.TextInput(attrs={'readonly': 'readonly'})
    )

    class Meta:
        model = models.RedemptionContract
        fields = "__all__"

    def clean(self):
        super().clean()

        if self.cleaned_data.get("address"):
            return

        compile_data = ScriptFunctions.compileRedemptionContract(dict(
            params=dict(
                authKeyId=self.cleaned_data["auth_token_id"],
                tokenCategory=self.cleaned_data["fiat_token"].category,
                oraclePublicKey=self.cleaned_data["price_oracle_pubkey"],
            ),
            options=dict(network=settings.BCH_NETWORK, addressType="p2sh32"),
        ))
        self.cleaned_data["address"] = compile_data["address"]


class TreasuryContractForm(forms.ModelForm):
    address = forms.CharField(
        max_length=100, required=False,
        widget=forms.TextInput(attrs={'readonly': 'readonly'})
    )
    version = forms.ChoiceField(choices=models.TreasuryContract.Version.choices)
    anyhedge_base_bytecode = forms.CharField(
        required=False, widget=forms.Textarea(attrs={'readonly': 'readonly'}),
    )
    anyhedge_contract_version = forms.CharField(
        required=False, widget=forms.TextInput(attrs={'readonly': 'readonly'}),
    )

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

    def compile_contract_from_data(self, data):
        version = data["version"]
        anyhedge_base_bytecode = None
        anyhedge_contract_version = None
        pubkeys = [
            data["pubkey1"], data["pubkey2"], data["pubkey3"], data["pubkey4"], data["pubkey5"]
        ]

        if version == "v2":
            result = ScriptFunctions.getAnyhedgeBaseBytecode()
            anyhedge_base_bytecode = result["bytecode"]
            anyhedge_contract_version = result["version"]

        compile_opts = dict(
            params=dict(
                authKeyId=data["auth_token_id"],
                pubkeys=pubkeys,
                anyhedgeBaseBytecode=anyhedge_base_bytecode,
            ),
            options=dict(version=version, network=settings.BCH_NETWORK, addressType="p2sh32"),
        )

        compile_data = ScriptFunctions.compileTreasuryContract(compile_opts)
        return compile_data, anyhedge_base_bytecode, anyhedge_contract_version

    def clean(self):
        super().clean()

        if self.cleaned_data.get("address"):
            return

        compile_data, ah_base_bytecode, ah_version = self.compile_contract_from_data(
            self.cleaned_data,
        )

        self.cleaned_data["address"] = compile_data["address"]
        self.cleaned_data["anyhedge_base_bytecode"] = ah_base_bytecode
        self.cleaned_data["anyhedge_contract_version"] = ah_version



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
