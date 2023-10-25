import json
import pytz
import bitcoin
from uuid import uuid4
from datetime import datetime
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from vouchers.serializers import VaultSerializer
from main.models import Address
from .models import (
    LinkedDeviceInfo,
    UnlinkDeviceRequest,
    PosDevice,
    Location,
    Merchant,
    Branch,
)
from .utils.broadcast import broadcast_transaction
from .utils.totp import generate_pos_device_totp
from .utils.websocket import send_device_update


REDIS_CLIENT = settings.REDISKV


def get_address_or_err(address):
    address = Address.objects.filter(address=address)
    if address.exists():
        return address.first()
    raise serializers.ValidationError('receiving_address does not exist')


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


class PosDeviceLinkRequestSerializer(serializers.Serializer):
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

        return data

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


class PosDeviceSerializer(serializers.ModelSerializer):
    posid = serializers.IntegerField(help_text="Resolves to a new posid if negative value")
    wallet_hash = serializers.CharField()
    name = serializers.CharField(required=False)
    branch_id = serializers.IntegerField(required=False, allow_null=True)
    linked_device = LinkedDeviceInfoSerializer(read_only=True)

    class Meta:
        model = PosDevice
        fields = [
            "posid",
            "wallet_hash",
            "name",
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

    def validate(self, data):
        wallet_hash = data["wallet_hash"]
        branch_id = data.get("branch_id", None)
        if branch_id:
            try:
                Branch.objects.get(merchant__wallet_hash=wallet_hash, id=branch_id)
            except Branch.DoesNotExist:
                raise serializers.ValidationError("branch_id under merchant wallet_hash not found")
        else:
            merchant = Merchant.objects.filter(wallet_hash=wallet_hash).first()
            if not merchant:
                raise serializers.ValidationError(dict(branch_id="Unable to create default branch"))
            main_branch, _ = merchant.get_or_create_main_branch()
            data["branch_id"] = main_branch.id

        return data

    def create(self, validated_data, *args, **kwargs):
        wallet_hash = validated_data["wallet_hash"]
        posid = validated_data["posid"]

        if posid < 0:
            posid = PosDevice.find_new_posid(wallet_hash)
            if posid is None:
                raise serializers.ValidationError("unable to find new posid")
            validated_data["posid"] = posid

        try:
            instance = PosDevice.objects.get(posid=posid, wallet_hash=wallet_hash)
            instance = super().update(instance, validated_data)
            send_device_update(instance, action="update")
            return instance
        except PosDevice.DoesNotExist:
            pass

        instance = super().create(validated_data, *args, **kwargs)
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
            "country",
            "longitude",
            "latitude",
        ]


class MerchantListSerializer(serializers.ModelSerializer):
    location = LocationSerializer(required=False)
    last_transaction_date = serializers.CharField()
    vault = VaultSerializer(required=False)
    logo_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Merchant
        fields = [
            "id",
            "name",
            "location",
            "gmap_business_link",
            "last_transaction_date",
            "receiving_pubkey",
            "signer_pubkey",
            "vault",
            "logo_url",
        ]
    
    def get_logo_url(self, obj):
        if obj.logo:
            return f'{settings.DOMAIN}{obj.logo.url}'
        return None


class MerchantSerializer(serializers.ModelSerializer):
    location = LocationSerializer(required=False)
    wallet_hash = serializers.CharField() # to supress unique validation
    vault = VaultSerializer(required=False)

    class Meta:
        model = Merchant
        fields = [
            "id",
            "wallet_hash",
            "name",
            "primary_contact_number",
            "location",
            "receiving_pubkey",
            "signer_pubkey",
            "vault",
        ]

        read_only_fields = ('vault', )


    @transaction.atomic()
    def create(self, validated_data):
        wallet_hash = validated_data["wallet_hash"]
        existing_merchant = Merchant.objects.filter(wallet_hash=wallet_hash).first()
        if existing_merchant:
            return self.update(existing_merchant, validated_data)

        location_data = validated_data.pop("location", None)
        if location_data:
            location_serializer = LocationSerializer(data=location_data)
            if not location_serializer.is_valid():
                raise serializers.ValidationError({ "location": location_serializer.errors })
            validated_data["location"] = location_serializer.save()

        instance = super().create(validated_data)
        instance.get_or_create_main_branch()
        return instance

    @transaction.atomic()
    def update(self, instance, validated_data):
        location_data = validated_data.pop("location", None)

        if location_data:
            location_serializer = LocationSerializer(instance.location, data=location_data, partial=self.partial)
            if not location_serializer.is_valid():
                raise serializers.ValidationError({ "location": location_serializer.errors })
            validated_data["location"] = location_serializer.save()

        return super().update(instance, validated_data)


class BranchMerchantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Merchant
        fields = [
            "id",
            "wallet_hash",
            "name",
        ]


class BranchSerializer(serializers.ModelSerializer):
    merchant_wallet_hash = serializers.CharField(write_only=True)
    merchant = BranchMerchantSerializer(read_only=True)
    location = LocationSerializer(required=False)

    class Meta:
        model = Branch
        fields = [
            "id",
            "merchant_wallet_hash",
            "merchant",
            "is_main",
            "name",
            "location",
        ]

    def validate_merchant_wallet_hash(self, value):
        if self.instance and self.instance.merchant.wallet_hash != value:
            raise serializers.ValidationError("merchant wallet hash is not editable")

        try:
            Merchant.objects.get(wallet_hash=value)
        except Merchant.DoesNotExist:
            raise serializers.ValidationError("merchant not found")
        return value


    @transaction.atomic()
    def create(self, validated_data):
        merchant_wallet_hash = validated_data.pop("merchant_wallet_hash")
        try:
            validated_data["merchant"] = Merchant.objects.get(wallet_hash=merchant_wallet_hash)
        except Merchant.DoesNotExist:
            raise serializers.ValidationError("merchant not found")

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
