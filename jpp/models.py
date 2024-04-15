import uuid
from django.db import models
from django.urls import reverse
from django.contrib.postgres.fields import JSONField
from cashaddress import convert

# Create your models here.
class Invoice(models.Model):
    URL_TYPE_BCOM = "bitcoin.com"
    URL_TYPE_BITPAY = "bitpay"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True, editable=False)
    required_fee_per_byte = models.FloatField(default=1.1)
    memo = models.TextField(null=True, blank=True)
    time = models.DateTimeField(auto_now_add=True)
    expires = models.DateTimeField()

    merchant_data = JSONField(null=True, blank=True)

    @property
    def network(self):
        return "main"

    @property
    def currency(self):
        return "BCH"

    @property
    def total_satoshis(self):
        return self.outputs.aggregate(total=models.Sum("amount"))["total"]

    @property
    def total_bch(self):
        return round(self.total_satoshis / 10 ** 8, 8)

    def get_absolute_uri(self, request, url_type=None):
        return request.build_absolute_uri(self.get_url_path(url_type=url_type))

    def get_url_path(self, url_type=None):
        view_name = "invoices-detail"
        if url_type == self.URL_TYPE_BCOM:
            view_name = "invoice-protobuf"
        elif url_type == self.URL_TYPE_BITPAY:
            view_name = "invoice-bitpay"

        return reverse(view_name, kwargs={ "uuid": self.uuid.hex })

    def payment_options(self, payment_url=None):
        return {
            "time": str(self.time),
            "expires": str(self.expires),
            "memo": self.memo,
            "paymentUrl": payment_url,
            "paymentId": self.uuid.hex,
            "paymentOptions": [
                {
                    "chain": "BCH",
                    "currency": "BCH",
                    "network": self.network,
                    "estimatedAmount": 315200,
                    "requiredFeeRate": self.required_fee_per_byte,
                    "decimals": 8,
                    # "minerFee": 0,
                    # "selected": False,
                }
            ]
        }

    def as_bitpay(self, payment_url=None):
        outputs = []
        for output in self.outputs.all():
            outputs.append({
                "address": convert.to_legacy_address(output.address),
                "amount": output.amount,
            })

        return {
            "time": str(self.time),
            "expires": str(self.expires),
            "memo": self.memo,
            "paymentUrl": payment_url,
            "paymentId": self.uuid.hex,
            "chain": "BCH",
            "network": "main",
            "instructions": [
                {
                    "type": "transaction",
                    "requiredFeeRate": self.required_fee_per_byte,
                    "outputs": outputs,
                }
            ]
        }


class InvoiceOutput(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="outputs")
    amount = models.BigIntegerField()
    address = models.CharField(max_length=70)


class InvoicePayment(models.Model):
    invoice = models.OneToOneField(Invoice, on_delete=models.CASCADE, related_name="payment")

    txid = models.CharField(max_length=70)
    memo = models.TextField(null=True, blank=True)
    paid_at = models.DateTimeField()


class InvoicePaymentRefundOutput(models.Model):
    invoice_payment = models.ForeignKey(InvoicePayment, on_delete=models.CASCADE, related_name="refund_to")
    amount = models.BigIntegerField()
    address = models.CharField(max_length=70)
