from django.utils.encoding import smart_text
from rest_framework import renderers


class MediaTypes:
    class BCom:
        PaymentRequest = "application/bitcoincash-paymentrequest"
        Payment = "application/bitcoincash-payment"
        PaymentACK = "application/bitcoincash-paymentack"

    class BitPay:
        PaymentRequest = "application/payment-request"
        PaymentOptions = "application/payment-options"
        PaymentVerification = "application/payment-verification"
        Payment = "application/payment"



class ProtobufRenderer(renderers.BaseRenderer):
    accept = [
        "application/octet-stream",
    ]
    format = "binary"
    charset = None

    def render(self, data, *args, accepted_media_type=None, renderer_context=None, **kwargs):
        if isinstance(data, (dict, list, str)):
            return str(data).encode()
        return data


class BComPaymentRequestRenderer(ProtobufRenderer):
    media_type = MediaTypes.BCom.PaymentRequest

class BComPaymentACKRenderer(ProtobufRenderer):
    media_type = MediaTypes.BCom.PaymentACK

class BitPayPaymentOptionsRenderer(renderers.JSONRenderer):
    media_type = MediaTypes.BitPay.PaymentOptions

class BitPayPaymentRequestRenderer(renderers.JSONRenderer):
    media_type = MediaTypes.BitPay.PaymentRequest
