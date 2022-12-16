import binascii
import requests
import bitcoin
import cashaddress
from django.utils import timezone

from . import paymentrequest_pb2 as pb2


class PaymentRequest:
    REQUEST_HEADERS = { "Accept": "application/bitcoincash-paymentrequest" }

    @classmethod
    def get_payment_request(cls, url):
        data, error = None, None
        try:
            response = requests.get(url, headers=cls.REQUEST_HEADERS)
            response.raise_for_status()
            data = response.content
        except requests.exceptions.RequestException as e:
            error = str(e)

        return cls(data, error=error)

    def __init__(self, data, error=None):
        self.raw = data
        self.error = error
        self.parse()
        self.tx = None

    def __str__(self):
        return str(self.raw)

    def parse(self):
        if self.error:
            return

        try:
            self.data = pb2.PaymentRequest()
            self.data.ParseFromString(self.raw)
        except:
            self.error = "Cannot parse payment request"
            return

        self.details = pb2.PaymentDetails()
        self.details.ParseFromString(self.data.serialized_payment_details)
        self.network = self.details.network
        self.outputs = []
        for o in self.details.outputs:
            script_hex = binascii.hexlify(o.script).decode()
            address = bitcoin.transaction.script_to_address(script_hex)
            cashaddr = cashaddress.convert.to_cash_address(address)
            self.outputs.append({ "address": cashaddr, "amount": o.amount })
        self.memo = self.details.memo
        self.payment_url = self.details.payment_url

        self.time = timezone.datetime.fromtimestamp(self.details.time).replace(tzinfo=timezone.pytz.UTC)
        self.expires = timezone.datetime.fromtimestamp(self.details.expires).replace(tzinfo=timezone.pytz.UTC)
