import json
import pytz
import bitcoin
from uuid import uuid4
from datetime import datetime
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum
from rest_framework import serializers, exceptions
from bitcash.keygen import public_key_to_address

from vouchers.serializers import *
from vouchers.models import Voucher
from vouchers.vault import create_device_vault, create_merchant_vault

from main.models import CashNonFungibleToken, Wallet, Address

from .models import *
from .permissions import HasMinPaytacaVersionHeader
from .utils.broadcast import broadcast_transaction
from .utils.totp import generate_pos_device_totp
from .utils.websocket import send_device_update


REDIS_CLIENT = settings.REDISKV


def get_address_or_err(address):
    address = Address.objects.filter(address=address)
    if address.exists():
        return address.first()
    raise serializers.ValidationError('receiving_address does not exist')


class PermissionSerializerMixin:
    def is_valid(self, *args, **kwargs):
        response = super().is_valid(*args, **kwargs)
        self.check_permissions()
        return response

    def check_permissions(self):
        raise Exception("Not implemented")


class TimestampField(serializers.IntegerField):
    def to_representation(self, value):
        return datetime.timestamp(value)

    def to_internal_value(self, data):
        return datetime.fromtimestamp(data).replace(tzinfo=pytz.UTC)


class SummaryRecordSerializer(serializers.Serializer):
    year = serializers.IntegerField()
    month = serializers.IntegerField()
    day = serializers.IntegerField(required=False)
    total = serializers.FloatField()
    total_market_value = serializers.FloatField(required=False)
    currency = serializers.CharField(required=False)
    count = serializers.IntegerField()


class SalesSummarySerializer(serializers.Serializer):
    wallet_hash = serializers.CharField()
    posid = serializers.IntegerField(required=False)
    range_type = serializers.CharField()
    timestamp_from = TimestampField(required=False)
    timestamp_to = TimestampField(required=False)
    data = SummaryRecordSerializer(many=True)


class SuspendDeviceSerializer(serializers.Serializer):
    is_suspended = serializers.BooleanField()

    def __init__(self, *args, pos_device=None, **kwargs):
        self.pos_device = pos_device
        return super().__init__(*args, **kwargs)

    def validate(self, data):
        if not isinstance(self.pos_device, PosDevice):
            raise serializers.ValidationError("pos device not found")

        if not self.pos_device.linked_device:
            raise serializers.ValidationError("pos device is not linked")

        return data

    def save(self):
        is_suspended = self.validated_data["is_suspended"]
        if self.pos_device.linked_device.is_suspended != is_suspended:
            self.pos_device.linked_device.is_suspended = is_suspended
            self.pos_device.linked_device.save()
            self.pos_device.linked_device.refresh_from_db()

            send_device_update(self.pos_device, action = "suspend" if is_suspended else "unsuspend")
        return self.pos_device


class PosDeviceLinkSerializer(serializers.Serializer):
    code = serializers.CharField()
    expires = serializers.CharField(read_only=True)


class PosDeviceLinkRequestSerializer(PermissionSerializerMixin, serializers.Serializer):
    wallet_hash = serializers.CharField()
    posid = serializers.IntegerField()
    encrypted_xpubkey = serializers.CharField()
    signature = serializers.CharField()

    def validate(self, data):
        wallet_hash = data["wallet_hash"]
        posid = data["posid"]

        pos_device = PosDevice.objects.filter(wallet_hash=wallet_hash, posid = posid).first()
        if not pos_device:
            raise serializers.ValidationError("pos device does not exist")
        if pos_device.linked_device:
            raise serializers.ValidationError("pos device is already linked")

        self.pos_device = pos_device
        return data

    def check_permissions(self):
        if not self.context or "request" not in self.context:
            return

        request = self.context["request"]

        # older versions didnt need authentication
        if HasMinPaytacaVersionHeader.on_request(request):
            return

        wallet = request.user

        if not isinstance(wallet, Wallet) or not wallet.is_authenticated:
            raise exceptions.PermissionDenied()

        merchant = None
        if self.pos_device:
            merchant = self.pos_device.merchant

        if not merchant or merchant.wallet_hash != wallet.wallet_hash:
            raise exceptions.PermissionDenied("Instance does not belong to authenticated wallet")

    @classmethod
    def generate_redis_key(cls, code):
        return f"posdevicelink:{code}"

    @classmethod
    def retrieve_link_request_data(cls, code):
        redis_key = cls.generate_redis_key(code)
        encoded_data = REDIS_CLIENT.get(redis_key)
        try:
            return json.loads(encoded_data)
        except (json.JSONDecodeError, TypeError):
            return None

    def save_link_request(self):
        code_ttl = 60 * 5 # seconds
        code = uuid4().hex
        redis_key = self.generate_redis_key(code)
        data = json.dumps(self.validated_data).encode()
        REDIS_CLIENT.set(redis_key, data, ex=code_ttl)
        now = timezone.now()
        expires = now + timezone.timedelta(seconds=code_ttl)
        return { "code": code, "expires": expires.timestamp() }


class UnlinkDeviceSerializer(serializers.Serializer):
    verifying_pubkey = serializers.CharField()

    def __init__(self, *args, pos_device=None, **kwargs):
        self.pos_device = pos_device
        return super().__init__(*args, **kwargs)

    def validate(self, data):
        if not self.pos_device.linked_device:
            raise serializers.ValidationError("pos device is not linked")
        if not self.pos_device.linked_device.get_unlink_request():
            raise serializers.ValidationError("pos device has no unlink request")

        verifying_pubkey = data["verifying_pubkey"]
        unlink_request = self.pos_device.linked_device.get_unlink_request()
        if not bitcoin.ecdsa_verify(unlink_request.message, unlink_request.signature, verifying_pubkey):
            raise serializers.ValidationError("invalid verifying pubkey")

        return data

    def save(self):
        self.pos_device.linked_device.delete()
        self.pos_device.refresh_from_db()
        send_device_update(self.pos_device, action="unlink")
        return self.pos_device


class UnlinkDeviceRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnlinkDeviceRequest
        fields = [
            "id",
            "force",
            "signature",
            "nonce",
            "updated_at",
        ]

        extra_kwargs = {
            "updated_at": {
                "read_only": True,
            },
        }

    def __init__(self, *args, linked_device_info=None, **kwargs):
        self.linked_device_info = linked_device_info
        return super().__init__(*args, **kwargs)

    def validate_nonce(self, value):
        if value < 0 or value > 2 ** 31:
            raise serializers.ValidationError(f"nonce must be between 0 and 2^31")
        return value

    def validate(self, data):
        data["linked_device_info"] = self.linked_device_info
        return data

    def create(self, validated_data):
        linked_device_info = validated_data["linked_device_info"]
        instance = None
        try:
            instance = UnlinkDeviceRequest.objects.get(linked_device_info=linked_device_info)
        except UnlinkDeviceRequest.DoesNotExist:
            pass

        if instance:
            return super().update(instance, validated_data)
        return super().create(validated_data)


class LinkedDeviceInfoSerializer(serializers.ModelSerializer):
    verifying_pubkey = serializers.CharField(write_only=True)
    link_code = serializers.CharField()
    unlink_request = UnlinkDeviceRequestSerializer(read_only=True)

    class Meta:
        model = LinkedDeviceInfo
        fields = [
            "verifying_pubkey",
            "link_code",
            "device_id",
            "name",
            "device_model",
            "os",
            "is_suspended",
            "unlink_request",
        ]

        extra_kwargs = {
            "is_suspended": {
                "read_only": True,
            },
        }

    def remove_link_code_data(self):
        if not self.instance:
            return
        redis_key = f"posdevicelink:{self.instance.link_code}"
        encoded_data = REDIS_CLIENT.delete(redis_key)

    def validate(self, data):
        verifying_pubkey = data.pop("verifying_pubkey")
        link_code = data["link_code"]
        link_code_data = PosDeviceLinkRequestSerializer.retrieve_link_request_data(link_code)
        data_serializer = PosDeviceLinkRequestSerializer(data=link_code_data)
        if not data_serializer.is_valid():
            raise serializers.ValidationError("data from link code is invalid")

        encrypted_xpubkey = data_serializer.validated_data["encrypted_xpubkey"]
        signature = data_serializer.validated_data["signature"]
        if not bitcoin.ecdsa_verify(encrypted_xpubkey, signature, verifying_pubkey):
            raise serializers.ValidationError("invalid verifying pubkey")

        data["link_code_data"] = data_serializer.validated_data

        wallet_hash = data["link_code_data"]["wallet_hash"]
        posid = data["link_code_data"]["posid"]

        pos_device = PosDevice.objects.filter(wallet_hash=wallet_hash, posid=posid).first()
        if not pos_device:
            raise serializers.ValidationError("pos device not found")

        if pos_device.linked_device and pos_device.linked_device != link_code:
            raise serializers.ValidationError("pos device is already linked")

        return data

    @transaction.atomic
    def create(self, validated_data):
        link_code = validated_data["link_code"]
        link_code_data = validated_data.pop("link_code_data")

        wallet_hash = link_code_data["wallet_hash"]
        posid = link_code_data["posid"]

        pos_device = PosDevice.objects.filter(wallet_hash=wallet_hash, posid=posid).first()
        if not pos_device:
            raise ValidationError("pos device not found")

        if pos_device.linked_device and pos_device.linked_device.link_code == link_code:
            instance = super().update(pos_device.linked_device, validated_data)
        else:
            instance = super().create(validated_data)
            pos_device.linked_device = instance
            pos_device.save()

        return instance


class PosDeviceVaultAddressSerializer(serializers.Serializer):
    posid = serializers.IntegerField()
    address = serializers.CharField(max_length=70)

    def validate_posid(self, value):
        if value < 0: raise serializers.ValidationError('POSID should be >= 0')
        return value

    def validate_address(self, value):
        address = Address.objects.filter(address=value)
        if not address.exists(): raise serializers.ValidationError('Address is not subscribed')
        return value


class PosDeviceSerializer(PermissionSerializerMixin, serializers.ModelSerializer):
    posid = serializers.IntegerField(help_text="Resolves to a new posid if negative value")
    wallet_hash = serializers.CharField()
    vault = PosDeviceVaultSerializer(read_only=True)
    pubkey = serializers.CharField(write_only=True, required=False, help_text="POS Device Vault pubkey (1-<POSID>th address)")
    name = serializers.CharField(required=False)
    merchant_id = serializers.PrimaryKeyRelatedField(
        queryset=Merchant.objects, source="merchant", required=False,
    )
    branch_id = serializers.IntegerField(required=False, allow_null=True)
    linked_device = LinkedDeviceInfoSerializer(read_only=True)

    class Meta:
        model = PosDevice
        fields = [
            "posid",
            "wallet_hash",
            "pubkey",
            "vault",
            "name",
            "merchant_id",
            "branch_id",
            "linked_device",
        ]

    def __init__(self, *args, supress_merchant_info_validations=False, **kwargs):
        self.supress_merchant_info_validations = supress_merchant_info_validations
        return super().__init__(*args, **kwargs)
    
    def get_unique_together_validators(self):
        """Overriding method to disable unique together checks"""
        return []

    def validate_posid(self, value):
        if self.instance and self.instance.posid != value:
            raise serializers.ValidationError("editing posid is not allowed")
        return value

    def validate_wallet_hash(self, value):
        if self.instance and self.instance.wallet_hash != value:
            raise serializers.ValidationError("editing posid is not allowed")

        if not self.supress_merchant_info_validations:
            if not Merchant.objects.filter(wallet_hash = value).exists():
                raise serializers.ValidationError("Wallet hash does not have merchant information", code="missing_merchant_info")

        return value

    def validate_branch_id(self, value):
        if not value:
            return value

        try:
            Branch.objects.get(id=value)
        except Branch.DoesNotExist:
            raise serializers.ValidationError("branch not found")
        return value

    def resolve_merchant(self, data):
        merchant = data.get("merchant")
        
        if not merchant and self.instance and self.instance.merchant:
            merchant = self.instance.merchant

        if not merchant:
            wallet_hash = data["wallet_hash"]
            merchants = Merchant.objects.filter(wallet_hash=wallet_hash)
            if merchants.count() > 1:
                raise serializers.ValidationError("Unable to resolve merchant for device")
            merchant = merchants.first()

        return merchant

    def validate(self, data):
        wallet_hash = data["wallet_hash"]

        merchant = self.resolve_merchant(data)
        data["merchant"] = merchant

        if merchant.wallet_hash != wallet_hash:
            raise serializers.ValidationError("Wallet hash does not match with merchant")

        branch_id = data.get("branch_id", None)
        if branch_id:
            try:
                Branch.objects.get(merchant_id=merchant.id, id=branch_id)
            except Branch.DoesNotExist:
                raise serializers.ValidationError("Branch does not belong to merchant")
        else:
            main_branch, _ = merchant.get_or_create_main_branch()
            data["branch_id"] = main_branch.id

        return data

    def check_permissions(self):
        if not self.context or "request" not in self.context:
            return

        request = self.context["request"]

        # older versions didnt need authentication
        if HasMinPaytacaVersionHeader.on_request(request):
            return

        wallet = request.user

        if not isinstance(wallet, Wallet) or not wallet.is_authenticated:
            raise exceptions.PermissionDenied()

        merchant = None
        if self.instance:
            merchant = self.instance.merchant
        else:
            merchant = self.validated_data["merchant"]

        if not merchant or merchant.wallet_hash != wallet.wallet_hash:
            raise exceptions.PermissionDenied("Instance does not belong to authenticated wallet")

    def create(self, validated_data, *args, **kwargs):
        wallet_hash = validated_data["wallet_hash"]
        posid = validated_data["posid"]

        if posid < 0:
            posid = PosDevice.find_new_posid(wallet_hash)
            if posid is None:
                raise serializers.ValidationError("unable to find new posid")
            validated_data["posid"] = posid

        pubkey = validated_data.get('pubkey')
        if 'pubkey' in validated_data.keys(): del validated_data['pubkey']

        try:
            instance = PosDevice.objects.get(posid=posid, wallet_hash=wallet_hash)
            instance = super().update(instance, validated_data)
            create_device_vault(instance.id, pubkey)
            send_device_update(instance, action="update")
            return instance
        except PosDevice.DoesNotExist:
            pass

        instance = super().create(validated_data, *args, **kwargs)
        create_device_vault(instance.id, pubkey)
        send_device_update(instance, action="create")
        return instance


class POSDevicePaymentSerializer(serializers.Serializer):
    posid = serializers.IntegerField(help_text='Resolves to a new posid if negative value')
    # NOTE: either receiving_address (latest POS) or wallet_hash (old POS versions)
    receiving_address = serializers.CharField(required=False)
    wallet_hash = serializers.CharField(required=False)

    def __init__(self, *args, supress_merchant_info_validations=False, **kwargs):
        self.supress_merchant_info_validations = supress_merchant_info_validations
        return super().__init__(*args, **kwargs)

    def validate_posid(self, value):
        if self.instance and self.instance.posid != value:
            raise serializers.ValidationError("editing posid is not allowed")
        return value

    def validate_wallet_hash(self, value):
        if self.instance and self.instance.wallet_hash != value:
            raise serializers.ValidationError("editing posid is not allowed")

        if not self.supress_merchant_info_validations:
            if not Merchant.objects.filter(wallet_hash = value).exists():
                raise serializers.ValidationError("Wallet hash does not have merchant information", code="missing_merchant_info")
        return value


class CreatePosPaymentRequestSerializer(serializers.Serializer):
    pos_device = POSDevicePaymentSerializer()
    amount = serializers.FloatField()
    receiving_address = serializers.CharField()

    def save(self):
        validated_data = self.validated_data
        posid = validated_data['pos_device'].get('posid')
        wallet_hash = validated_data['pos_device'].get('wallet_hash')

        # some payment requests might not be deleted on POS, in the case of internet failure on the device
        # so we delete old requests of the device
        pos_device = PosDevice.objects.get(posid=posid, wallet_hash=wallet_hash)
        old_uncancelled_requests = PosPaymentRequest.objects.filter(pos_device=pos_device)
        old_uncancelled_requests.delete()

        payment_request = PosPaymentRequest.objects.create(
            pos_device=pos_device,
            amount=validated_data['amount'],
            receiving_address=validated_data['receiving_address'],
        )
        return payment_request


class CancelPaymentRequestSerializer(serializers.Serializer):
    pos_device = POSDevicePaymentSerializer()


class UpdatePaymentRequestSerializer(serializers.Serializer):
    pos_device = POSDevicePaymentSerializer()
    amount = serializers.FloatField()
    

class PosPaymentRequestSerializer(serializers.ModelSerializer):
    pos_device = POSDevicePaymentSerializer()

    class Meta:
        model = PosPaymentRequest
        fields = [
            'pos_device',
            'amount',
            'receiving_address',
            'paid',
        ]


class POSPaymentSerializer(serializers.Serializer):
    transaction = serializers.CharField()
    otp = serializers.CharField(required=False)
    payment_timestamp = TimestampField()
    pos_device = POSDevicePaymentSerializer(supress_merchant_info_validations=True)

    def save(self):
        validated_data = self.validated_data
        otp = validated_data.get("otp", None)
        payment_timestamp = validated_data.get("payment_timestamp", timezone.now())
        pos_device_data = validated_data["pos_device"]
        posid = pos_device_data['posid']

        if 'receiving_address' in pos_device_data.keys():
            receiving_address = pos_device_data['receiving_address']
            address = get_address_or_err(receiving_address)
            wallet_hash = address.wallet.wallet_hash
        else:
            wallet_hash = pos_device_data['wallet_hash']

        response = {
            "success": False,
            "txid": "",
        }

        otp_timestamp = round(payment_timestamp.timestamp())
        response["otp_timestamp"] = otp_timestamp
        if otp is not None:
            if otp != generate_pos_device_totp(wallet_hash, posid, timestamp=otp_timestamp):
                raise serializers.ValidationError("Provided OTP does not match")
            response["otp_valid"] = True
        else:
            response["otp"] = generate_pos_device_totp(wallet_hash, posid, timestamp=otp_timestamp)

        broadcast_response = broadcast_transaction(validated_data["transaction"])
        if not broadcast_response["success"]:
            error_msg = "Failed to broadcast transaction"
            if "error" in broadcast_response and broadcast_response["error"]:
                error_msg = broadcast_response["error"]
            raise serializers.ValidationError(error_msg)

        response["success"] = True
        response["txid"] = broadcast_response["txid"]

        return response


class POSPaymentResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    txid = serializers.CharField()
    otp = serializers.CharField(required=False)
    otp_timestamp = serializers.IntegerField()
    otp_valid = serializers.CharField(required=False)


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = [
            "landmark",
            "location",
            "street",
            "city",
            "town",
            "province",
            "state",
            "country",
            "longitude",
            "latitude",
        ]


class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = '__all__'


class MerchantListSerializer(serializers.ModelSerializer):
    location = LocationSerializer(required=False)
    last_transaction_date = serializers.CharField()

    logos = serializers.SerializerMethodField()
    vouchers = serializers.SerializerMethodField()
    branch_count = serializers.IntegerField(read_only=True)
    pos_device_count = serializers.IntegerField(read_only=True)
    vault = MerchantVaultSerializer(read_only=True)
    minter = VerificationTokenMinterSerializer(read_only=True)
    
    class Meta:
        model = Merchant
        fields = [
            "id",
            "wallet_hash",
            "vault",
            "minter",
            "slug",
            "name",
            "location",
            "website_url",
            "category",
            "description",
            "gmap_business_link",
            "last_transaction_date",
            "vouchers",
            "logos",
            "last_update",
            "branch_count",
            "pos_device_count",
        ]
    
    def get_logos(self, obj):
        logos = {
            '30x30': obj.logo_30,
            '60x60': obj.logo_60,
            '90x90': obj.logo_90,
            '120x120': obj.logo_120
        }

        for key, logo in logos.items():
            if logo:
                logos[key] = f'{settings.DOMAIN}{logo.url}'
            else:
                logos[key] = None
                
        return logos

    def get_vouchers(self, obj):
        request = self.context['request']
        query_params = request.query_params
        voucher_nfts = CashNonFungibleToken.objects.all()

        if 'wallet_hash' in query_params.keys():
            wallet_hash = query_params.get('wallet_hash', '')
            if wallet_hash:
                voucher_nfts = voucher_nfts.filter(transaction__wallet__wallet_hash=wallet_hash)
                voucher_nfts = voucher_nfts.distinct()

        merchant_vouchers = Voucher.objects.filter(
            vault__merchant=obj,
            category__in=voucher_nfts.values('category'),
            commitment__in=voucher_nfts.values('commitment')
        )
        claimed_vouchers = merchant_vouchers.filter(claimed=True)
        unclaimed_vouchers = merchant_vouchers.filter(claimed=False, expired=False)

        vouchers_amount = merchant_vouchers.aggregate(total_amount=Sum('value'))
        claimed_vouchers_amount = claimed_vouchers.aggregate(total_amount=Sum('value'))
        unclaimed_vouchers_amount = unclaimed_vouchers.aggregate(total_amount=Sum('value'))

        total_vouchers_amount = vouchers_amount['total_amount']
        total_claimed_vouchers_amount = claimed_vouchers_amount['total_amount']
        total_unclaimed_vouchers_amount = unclaimed_vouchers_amount['total_amount']

        return {
            'count': {
                'total': merchant_vouchers.count(),
                'claimed': claimed_vouchers.count(),
                'unclaimed': unclaimed_vouchers.count()
            },
            'amount': {
                'total': total_vouchers_amount or 0,
                'claimed': total_claimed_vouchers_amount or 0,
                'unclaimed': total_unclaimed_vouchers_amount or 0
            }
        }


class MerchantSerializer(PermissionSerializerMixin, serializers.ModelSerializer):
    # temporary field: to prevent making multiple duplicate merchants
    # - wallet_hash was unique before, making a `get_or_create` behavior on this serializer
    # - can be removed once multiple merchant is implemented in paytaca-app
    allow_duplicates = serializers.BooleanField(write_only=True, default=False)

    location = LocationSerializer(required=False)

    branch_count = serializers.IntegerField(read_only=True)
    pos_device_count = serializers.IntegerField(read_only=True)

    pubkey = serializers.CharField(
        write_only=True,
        required=False,
        help_text='Merchant Vault pubkey (0th address)'
    )
    minter_address = serializers.CharField(write_only=True, required=False)
    minter_category = serializers.CharField(write_only=True, required=False)

    vault = MerchantVaultSerializer(read_only=True)
    minter = VerificationTokenMinterSerializer(read_only=True)

    class Meta:
        model = Merchant
        fields = [
            "id",
            "vault",
            "minter",
            "wallet_hash",
            "name",
            "website_url",
            "category",
            "description",
            "primary_contact_number",
            "location",

            "pubkey",
            "minter_address",
            "minter_category",

            "allow_duplicates", # temporary field
            "branch_count",
            "pos_device_count",
        ]

    def validate_wallet_hash(self, value):
        if self.instance and self.instance.wallet_hash != value:
            raise serializers.ValidationError("Updating this field is not allowed")
        return value

    def validate(self, data):
        # remove after changes stable
        allow_duplicates = data.pop("allow_duplicates", False)
        if not allow_duplicates and not self.instance:
            wallet_hash = data["wallet_hash"]
            existing_merchants = Merchant.objects.filter(wallet_hash=wallet_hash)
            if existing_merchants.count() > 1:
                raise serializers.ValidationError(
                    "Multiple merchants found, unable unable to select which merchant to update"
                )
            else:
                self.instance = existing_merchants.first()

        return data

    def check_permissions(self):
        if not self.context or "request" not in self.context:
            return
        
        request = self.context["request"]

        # older versions didnt need authentication
        if HasMinPaytacaVersionHeader.on_request(request):
            return

        wallet = request.user

        if not isinstance(wallet, Wallet) or not wallet.is_authenticated:
            raise exceptions.PermissionDenied("Not a wallet")

        wallet_hash = None
        if self.instance:
            wallet_hash = self.instance.wallet_hash
        else:
            wallet_hash = self.validated_data["wallet_hash"]

        if not wallet_hash or wallet_hash != wallet.wallet_hash:
            raise exceptions.PermissionDenied("Wallet hash does not match with authenticated wallet")

    @transaction.atomic()
    def create(self, validated_data):
        # wallet_hash = validated_data["wallet_hash"]
        # existing_merchant = Merchant.objects.filter(wallet_hash=wallet_hash).first()
        # if existing_merchant:
        #     return self.update(existing_merchant, validated_data)

        location_data = validated_data.pop("location", None)
        if location_data:
            location_serializer = LocationSerializer(data=location_data)
            if not location_serializer.is_valid():
                raise serializers.ValidationError({ "location": location_serializer.errors })
            validated_data["location"] = location_serializer.save()

        pubkey = validated_data.get('pubkey')
        minter_address = validated_data.get('minter_address')
        minter_category = validated_data.get('minter_category')
        data_keys = validated_data.keys()

        if 'pubkey' in data_keys: del validated_data['pubkey']
        if 'minter_address' in data_keys: del validated_data['minter_address']
        if 'minter_category' in data_keys: del validated_data['minter_category']

        instance = super().create(validated_data)
        instance.get_or_create_main_branch()
        create_merchant_vault(instance.id, pubkey, minter_address, minter_category)

        return instance

    @transaction.atomic()
    def update(self, instance, validated_data):
        location_data = validated_data.pop("location", None)

        if location_data:
            location_serializer = LocationSerializer(instance.location, data=location_data, partial=self.partial)
            if not location_serializer.is_valid():
                raise serializers.ValidationError({ "location": location_serializer.errors })
            validated_data["location"] = location_serializer.save()

        pubkey = validated_data.get('pubkey')
        minter_address = validated_data.get('minter_address')
        minter_category = validated_data.get('minter_category')
        data_keys = validated_data.keys()

        if 'pubkey' in data_keys: del validated_data['pubkey']
        if 'minter_address' in data_keys: del validated_data['minter_address']
        if 'minter_category' in data_keys: del validated_data['minter_category']

        instance = super().update(instance, validated_data)
        create_merchant_vault(instance.id, pubkey, minter_address, minter_category)

        return instance


class BranchMerchantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Merchant
        fields = [
            "id",
            "wallet_hash",
            "name",
        ]


class BranchSerializer(PermissionSerializerMixin, serializers.ModelSerializer):
    merchant_wallet_hash = serializers.CharField(required=False)
    merchant_id = serializers.PrimaryKeyRelatedField(
        queryset=Merchant.objects, write_only=True,
        source="merchant", required=False,
    )
    merchant = BranchMerchantSerializer(read_only=True)
    location = LocationSerializer(required=False)

    class Meta:
        model = Branch
        fields = [
            "id",
            "merchant_wallet_hash",
            "merchant_id",
            "merchant",
            "is_main",
            "name",
            "location",
        ]

    def validate_merchant_id(self, value):
        if self.instance and self.instance.merchant_id != value.id:
            raise serializers.ValidationError("merchant is not editable")
        return value

    def resolve_merchant(self, data):
        if "merchant" in data:
            return data["merchant"]
        if "merchant_wallet_hash" in data:
            merchants = Merchant.objects.filter(wallet_hash=data["merchant_wallet_hash"])
            if merchants.count() > 1:
                raise serializers.ValidationError("Found multiple merchants with the provide wallet hash, provide merchant ID instead")
            return merchants.first()
        raise serializers.ValidationError("Provide merchant ID or merchant wallet hash")

    def validate(self, data):
        merchant = self.resolve_merchant(data)
        data["merchant"] = merchant
        data.pop("merchant_wallet_hash", None)
        return data

    def check_permissions(self):
        if not self.context or "request" not in self.context:
            return
        
        request = self.context["request"]

        # older versions didnt need authentication
        if HasMinPaytacaVersionHeader.on_request(request):
            return

        wallet = request.user

        if not isinstance(wallet, Wallet) or not wallet.is_authenticated:
            raise exceptions.PermissionDenied()

        merchant = None
        if self.instance:
            merchant = self.instance.merchant
        else:
            merchant = self.validated_data["merchant"]

        if not merchant or merchant.wallet_hash != wallet.wallet_hash:
            raise exceptions.PermissionDenied("Instance does not belong to authenticated wallet")

    @transaction.atomic()
    def create(self, validated_data):
        location_data = validated_data.pop("location", None)
        if location_data:
            location_serializer = LocationSerializer(data=location_data)
            if not location_serializer.is_valid():
                raise serializers.ValidationError({ "location": location_serializer.errors })
            validated_data["location"] = location_serializer.save()

        is_main = validated_data.get("is_main", False)
        if is_main:
            Branch.objects.filter(merchant=validated_data["merchant"]).update(is_main=False)

        return super().create(validated_data)

    @transaction.atomic()
    def update(self, instance, validated_data):
        location_data = validated_data.pop("location", None)

        if location_data:
            location_serializer = LocationSerializer(instance.location, data=location_data, partial=self.partial)
            if not location_serializer.is_valid():
                raise serializers.ValidationError({ "location": location_serializer.errors })
            validated_data["location"] = location_serializer.save()

        is_main = validated_data.get("is_main", instance.is_main)
        if is_main:
            Branch.objects \
                .filter(merchant_id=instance.merchant_id) \
                .exclude(pk=instance.pk) \
                .update(is_main=False)

        return super().update(instance, validated_data)
