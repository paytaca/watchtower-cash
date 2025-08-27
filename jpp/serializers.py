import bitcoin
import binascii
from urllib.parse import urlencode
from django.utils import timezone
from django.db import transaction
from rest_framework import serializers
from main.utils.broadcast import broadcast_to_engagementhub

from .models import (
    Invoice,
    InvoiceOutput,
    InvoicePayment,
    InvoicePaymentRefundOutput,
)

from .utils.broadcast import (
    broadcast_transaction,
)
from .utils.protobuf import (
    script_to_address,
    deserialize_payment_pb,
)

from .utils.verify import (
    VerifyError,
    verify_tx_hex,
    tx_exists,
)

from main.models import (
    Wallet, Address,
)
from notifications.utils.send import (
    send_push_notification_to_wallet_hashes,
    NotificationTypes,
)


class InvoiceVerifySerializer(serializers.Serializer):
    raw_tx_hex = serializers.CharField(write_only=True)
    valid = serializers.BooleanField(read_only=True)
    error = serializers.CharField(read_only=True)

    def __init__(self, *args, invoice=None, **kwargs):
        self.invoice = invoice
        super().__init__(*args, **kwargs)

    def save(self):
        validated_data = self.validated_data
        raw_tx_hex = self.validated_data["raw_tx_hex"]
        try:
            verify_tx_hex(self.invoice, raw_tx_hex)
            validated_data["valid"] = True
        except VerifyError as verify_error:
            validated_data["valid"] = False
            validated_data["error"] = str(verify_error)

        self.instance = validated_data
        return self.instance


class OutputTokenNftSerializer(serializers.Serializer):
    capability = serializers.CharField()
    commitment = serializers.CharField()

class OutputTokenSerializer(serializers.Serializer):
    category = serializers.CharField()
    amount = serializers.IntegerField()
    nft = OutputTokenNftSerializer(required=False)


class OutputSerializer(serializers.Serializer):
    amount = serializers.IntegerField()
    address = serializers.CharField()
    token = OutputTokenSerializer(required=False)

    class Meta:
        ref_name = "JPPOutputSerializer"


class InvoicePaymentSerializer(serializers.ModelSerializer):
    refund_to = OutputSerializer(many=True, required=False)
    raw_tx_hex = serializers.CharField(write_only=True)

    class Meta:
        model = InvoicePayment
        fields = [
            "txid",
            "raw_tx_hex",
            "memo",
            "paid_at",
            "refund_to",
        ]

        extra_kwargs = {
            "txid": {
                "read_only": True,
            },
            "paid_at": {
                "read_only": True,
            }
        }

    @classmethod
    def from_protobuf(cls, raw, *args, **kwargs):
        payment_pb = deserialize_payment_pb(raw)
        payment_data = { "raw_tx_hex": binascii.hexlify(payment_pb.transactions[0]).decode() }
        if payment_pb.memo:
            payment_data["memo"] = payment_pb.memo

        if payment_pb.merchant_data:
            payment_data["merchant_data"] = payment_pb.merchant_data

        if len(payment_pb.refund_to):
            payment_data["refund_to"] = []
            for output in payment_pb.refund_to:
                payment_data["refund_to"].append({
                    "address": script_to_address(output.script),
                    "amount": output.amount,
                })

        kwargs["data"] = payment_data
        return cls(*args, **kwargs)

    def __init__(self, *args, invoice=None, **kwargs):
        self.invoice = invoice
        super().__init__(*args, **kwargs)

    def validate(self, data):
        if not isinstance(self.invoice, Invoice):
            raise serializers.ValidationError("invalid invoice")

        try:
            if self.invoice.payment:
                raise serializers.ValidationError("invoice is already paid")
        except Invoice.payment.RelatedObjectDoesNotExist:
            pass

        if self.invoice.expires < timezone.now():
            raise serializers.ValidationError("invoice is expired")

        try:
            verify_tx_hex(self.invoice, data["raw_tx_hex"])
        except VerifyError as error:
            raise serializers.ValidationError(str(error))

        return data

    @transaction.atomic
    def create(self, validated_data):
        refund_to_data_list = validated_data.pop("refund_to", None)

        raw_tx_hex = validated_data.pop("raw_tx_hex", None)
        txid = bitcoin.txhash(raw_tx_hex)
        validated_data["invoice"] = self.invoice
        validated_data["txid"] = txid
        validated_data["paid_at"] = timezone.now()

        instance = super().create(validated_data)

        if isinstance(refund_to_data_list, list):
            for output_data in refund_to_data_list:
                output_data["invoice_payment"] = instance
                InvoicePaymentRefundOutput.objects.create(**output_data)

        if not tx_exists(txid):
            # raise serializers.ValidationError("Just rejecting broadcast")
            broadcast_response = broadcast_transaction(
                raw_tx_hex,
                invoice_uuid=self.invoice.uuid.hex,
            )
            if not broadcast_response["success"]:
                raise serializers.ValidationError(
                    broadcast_response.get("error", "Failed to broadcast transaction")
                )

        return instance


class InvoiceSerializer(serializers.ModelSerializer):
    payment_id = serializers.UUIDField(read_only=True, source="uuid", format="hex")
    payment_url = serializers.SerializerMethodField()
    network = serializers.CharField(read_only=True)
    currency = serializers.CharField(read_only=True)

    payment = InvoicePaymentSerializer(read_only=True)
    outputs = OutputSerializer(many=True)

    class Meta:
        model = Invoice
        fields = [
            "payment_id",
            "payment_url",
            "network",
            "currency",
            "required_fee_per_byte",
            "memo",
            "time",
            "expires",
            "outputs",
            "payment",
            "merchant_data",
        ]
        extra_kwargs = {
            "expires": {
                "read_only": True,
            },
        }

    def get_payment_url(self, obj):
        if self.context and "request" in self.context:
            return obj.get_absolute_uri(self.context["request"])
        return None

    def validate(self, data):
        if "outputs" not in data or len(data["outputs"]) <= 0:
            raise serializers.ValidationError("must have at least 1 output")
        return data

    def send_push_notification(self, instance):
        try:
            address = instance.merchant_data["address"]
        except (AttributeError, TypeError, KeyError):
            return

        wallet_hashes = Wallet.objects.filter(addresses__address=address) \
            .values_list("wallet_hash", flat=True) \
            .distinct()
        address_path = Address.objects.filter(address=address) \
            .values_list("address_path", flat=True) \
            .first()

        wallet_hashes = [*wallet_hashes]
        if not wallet_hashes:
            return

        payment_url_params = urlencode({
            "r": instance.get_absolute_uri(self.context["request"]),
        })
        extra = {
            "type": NotificationTypes.PAYMENT_REQUEST,
            "payment_url": f"bitcoincash:?{payment_url_params}",
        }

        if address_path:
            extra["use_address_path"] = address_path

        total_bch = abs(instance.total_bch)
        total_bch = f'{total_bch:.5f}'.rstrip('0').rstrip('.')

        title = "Payment Request"
        message = f"You have a payment request of {total_bch} BCH"

        broadcast_to_engagementhub({
            'title': title,
            'message': message,
            'wallet_hash': wallet_hashes,
            'notif_type': 'TR',
            'extra_data': extra['payment_url'],
            'date_posted': timezone.now().isoformat()
        })

        return send_push_notification_to_wallet_hashes(
            wallet_hashes,
            message,
            title=title,
            extra=extra,
        )

    def flatten_output_data(self, output_data):
        if "token" not in output_data: return output_data

        token_data = output_data.pop("token")
        output_data["category"] = token_data["category"]
        output_data["token_amount"] = token_data["amount"]
        if "nft" not in token_data: return output_data
        nft_data = token_data.pop("nft")
        output_data["capability"] = nft_data["capability"]
        output_data["commitment"] = nft_data["commitment"]
        return output_data

    @transaction.atomic
    def create(self, validated_data):
        output_data_list = validated_data.pop("outputs")
        validated_data["expires"] = timezone.now() + timezone.timedelta(minutes=30)
        instance = super().create(validated_data)

        for output_data in output_data_list:
            output_data = self.flatten_output_data(output_data)
            output_data["invoice"] = instance
            InvoiceOutput.objects.create(**output_data)

        self.send_push_notification(instance)
        return instance


class BitpayPaymentRequestSerializer(serializers.Serializer):
    chain = serializers.CharField()
    currency = serializers.CharField()


class BitPayPaymentSerializer(serializers.Serializer):
    class BitPayTransactionSerializer(serializers.Serializer):
        tx = serializers.CharField()
        weightedSize = serializers.IntegerField(required=False)

    chain = serializers.CharField()
    transactions = BitPayTransactionSerializer(many=True)
    currency = serializers.CharField(required=False)

    def __init__(self, *args, invoice=None, **kwargs):
        self.invoice = invoice
        super().__init__(*args, **kwargs)

    def verify(self):
        if len(self.validated_data["transactions"]) != 1:
            raise serializers.ValidationError("Request must include exactly one (1) transaction")

        raw_tx_hex = self.validated_data["transactions"][0]["tx"]
        try:
            verify_tx_hex(self.invoice, raw_tx_hex)
        except VerifyError as verify_error:
            raise serializers.ValidationError(str(verify_error))
    
        return { "payment": self.validated_data, "memo": "Payment appears valid" }

    def pay(self):
        if len(self.validated_data["transactions"]) != 1:
            raise serializers.ValidationError("Request must include exactly one (1) transaction")

        raw_tx_hex = self.validated_data["transactions"][0]["tx"]
        payment_serializer = InvoicePaymentSerializer(
            data={ "raw_tx_hex": raw_tx_hex },
            invoice=self.invoice,
        )
        payment_serializer.is_valid(raise_exception=True)
        payment_serializer.save()

        return {
            "payment": self.validated_data,
            "memo": "Transaction received"
        }
