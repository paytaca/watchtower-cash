from rest_framework import parsers

from .renderers import MediaTypes

class BComPaymentParser(parsers.BaseParser):
    media_type = MediaTypes.BCom.Payment

    def parse(self, stream, media_type=None, parser_context=None):
        """
        Simply return a string representing the body of the request.
        """
        # raise Exception(f"here:\n\tmedia_type={media_type}\n\tparser_context={parser_context}\n\tstream={stream}")
        # if media_type is not None and "application/bitcoincash-payment" in media_type:
        #     return stream.read()

        # return super().parse(stream, media_type=None, parser_context=None)
        return stream.read()

class BitPayPaymentRequestParser(parsers.JSONParser):
    media_type = MediaTypes.BitPay.PaymentRequest

class BitPayVerifyPaymentParser(parsers.JSONParser):
    media_type = MediaTypes.BitPay.PaymentVerification

class BitPayPaymentParser(parsers.JSONParser):
    media_type = MediaTypes.BitPay.Payment
