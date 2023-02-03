import json
import bitcoin
import binascii
from cashaddress import convert
from google.protobuf import json_format
from . import paymentrequest_pb2 as pb2


def script_to_address(script_bytes):
    script_hex = binascii.hexlify(script_bytes).decode()
    legacy_address = bitcoin.transaction.script_to_address(script_hex)
    return convert.to_cash_address(legacy_address)

def address_to_script(address):
    legacy_address = convert.to_legacy_address(address)
    script_hex = bitcoin.address_to_script(legacy_address)
    return binascii.unhexlify(script_hex)


def deserialize_payment_pb(raw):
    payment_pb = pb2.Payment()
    payment_pb.ParseFromString(raw)
    return payment_pb

def serialize_invoice_payment_ack(invoice_obj):
    payment_obj = None
    try:
        payment_obj = invoice_obj.payment
    except invoice_obj.__class__.payment.RelatedObjectDoesNotExist:
        return

    if not payment_obj:
        return

    payment_ack_pb = pb2.PaymentACK()
    payment_ack_pb.payment.transactions.append(binascii.unhexlify(payment_obj.txid))
    if payment_obj.memo:
        payment_ack_pb.payment.memo = payment_obj.memo

    if invoice_obj.merchant_data:
        payment_ack_pb.merchant_data = json.dumps(invoice_obj.merchant_data).encode()

    for output in payment_obj.refund_to.all():
        output_pb = pb2.Output()
        output_pb.script = address_to_script(output.address)
        output_pb.amount = output.amount
        payment_ack_pb.payment.refund_to.append(output_pb)

    return payment_ack_pb


def serialize_invoice(invoice_obj, payment_url=None):
    payment_details_pb = pb2.PaymentDetails()
    payment_details_pb.network = invoice_obj.network
    payment_details_pb.time = int(invoice_obj.time.timestamp())
    payment_details_pb.expires = int(invoice_obj.expires.timestamp())
    if not payment_url:
        payment_details_pb.payment_url = f"https://example.com/i/{invoice_obj.uuid.hex}"
    else:
        payment_details_pb.payment_url = payment_url

    if invoice_obj.memo:
        payment_details_pb.memo = invoice_obj.memo

    if invoice_obj.merchant_data:
        payment_details_pb.merchant_data = json.dumps(invoice_obj.merchant_data).encode()

    outputs = []
    for output in invoice_obj.outputs.all():
        output_pb = pb2.Output()
        output_pb.script = address_to_script(output.address)
        output_pb.amount = output.amount
        payment_details_pb.outputs.append(output_pb)

    payment_request_pb = pb2.PaymentRequest()
    payment_request_pb.serialized_payment_details = payment_details_pb.SerializeToString()

    return payment_request_pb
