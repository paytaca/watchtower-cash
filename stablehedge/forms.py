from django.db import transaction
from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError

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
            options=dict(
                network=settings.BCH_NETWORK,
                addressType="p2sh32",
                version=self.cleaned_data["version"],
            ),
        ))
        self.cleaned_data["address"] = compile_data["address"]


class TreasuryContractForm(forms.ModelForm):
    address = forms.CharField(
        max_length=100, required=False,
        widget=forms.TextInput(attrs={'readonly': 'readonly'})
    )
    version = forms.ChoiceField(
        choices=models.TreasuryContract.Version.choices,
        help_text="V2 will automatically create a RedemptionContract.V2",
    )
    anyhedge_base_bytecode = forms.CharField(
        required=False, widget=forms.Textarea(attrs={'readonly': 'readonly'}),
    )
    anyhedge_contract_version = forms.CharField(
        required=False, widget=forms.TextInput(attrs={'readonly': 'readonly'}),
    )

    redemption_contract_base_bytecode = forms.CharField(
        required=False, widget=forms.Textarea(attrs={'readonly': 'readonly'}),
    )
    redemption_contract_version = forms.CharField(
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

    def clean_fiat_token(self):
        version = self.cleaned_data.get("version")
        fiat_token = self.cleaned_data.get("fiat_token")
        if version == "v2" and not fiat_token:
            raise ValidationError("Required for v2")
        return fiat_token

    def clean_price_oracle_pubkey(self):
        version = self.cleaned_data.get("version")
        price_oracle_pubkey = self.cleaned_data.get("price_oracle_pubkey")
        if version == "v2" and not price_oracle_pubkey:
            raise ValidationError("Required for v2")
        return price_oracle_pubkey

    def compile_contract_from_data(self, data):
        # raise Exception(f"{data}")
        TreasuryContract = models.TreasuryContract
        RedemptionContract = models.RedemptionContract

        version = data["version"]
        anyhedge_base_bytecode = None
        anyhedge_contract_version = None

        redemption_contract_base_bytecode = None
        redemption_contract_version = None

        pubkeys = [
            data["pubkey1"], data["pubkey2"], data["pubkey3"], data["pubkey4"], data["pubkey5"]
        ]

        if version in [TreasuryContract.Version.V2]:
            result = ScriptFunctions.getAnyhedgeBaseBytecode()
            anyhedge_base_bytecode = result["bytecode"]
            anyhedge_contract_version = result["version"]

            result = ScriptFunctions.getRedemptionContractBaseBytecode(RedemptionContract.Version.V2)
            redemption_contract_base_bytecode = result["bytecode"]
            redemption_contract_version = result["version"]

        compile_opts = dict(
            params=dict(
                authKeyId=data["auth_token_id"],
                pubkeys=pubkeys,
                anyhedgeBaseBytecode=anyhedge_base_bytecode,
                redemptionTokenCategory=getattr(data.get("fiat_token"), "category", None),
                oraclePublicKey=data["price_oracle_pubkey"],
                redemptionContractBaseBytecode=redemption_contract_base_bytecode,
            ),
            options=dict(
                version=version,
                network=settings.BCH_NETWORK,
                redemptionContractBaseBytecodeVersion=redemption_contract_version,
                addressType="p2sh32",
            ),
        )

        compile_data = ScriptFunctions.compileTreasuryContract(compile_opts)
        return (
            compile_data,
            anyhedge_base_bytecode, anyhedge_contract_version,
            redemption_contract_base_bytecode, redemption_contract_version,
        )

    def clean(self):
        super().clean()

        if self.cleaned_data.get("address"):
            return

        compile_result = self.compile_contract_from_data(self.cleaned_data)
        (
            compile_data,
            ah_base_bytecode, ah_version,
            rc_base_bytecode, rc_version,
        ) = compile_result

        self.cleaned_data["address"] = compile_data["address"]
        self.cleaned_data["anyhedge_base_bytecode"] = ah_base_bytecode
        self.cleaned_data["anyhedge_contract_version"] = ah_version
        self.cleaned_data["redemption_contract_base_bytecode"] = rc_base_bytecode
        self.cleaned_data["redemption_contract_version"] = rc_version

    @transaction.atomic
    def save(self, *args, **kwargs):
        treasury_contract = super().save(*args, **kwargs)

        if treasury_contract.version == models.TreasuryContract.Version.V2:
            self.create_redemption_contract_from_treasury_contract(treasury_contract)

        return treasury_contract

    def create_redemption_contract_from_treasury_contract(self, treasury_contract):
        version = treasury_contract.redemption_contract_version
        treasury_contract.save()

        compile_data = ScriptFunctions.compileRedemptionContract(dict(
            params=dict(
                authKeyId=treasury_contract.auth_token_id,
                tokenCategory=treasury_contract.fiat_token.category,
                oraclePublicKey=treasury_contract.price_oracle_pubkey,
                treasuryContractAddress=treasury_contract.address,
            ),
            options=dict(version=version, network=settings.BCH_NETWORK, addressType="p2sh32"),
        ))

        rc_address = compile_data["address"]

        redemption_contract, _ = models.RedemptionContract.objects.update_or_create(
            treasury_contract=treasury_contract,
            defaults=dict(
                address=rc_address,
                version=version,
                auth_token_id=treasury_contract.auth_token_id,
                fiat_token=treasury_contract.fiat_token,
                price_oracle_pubkey=treasury_contract.price_oracle_pubkey,
            )
        )
        return redemption_contract



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
