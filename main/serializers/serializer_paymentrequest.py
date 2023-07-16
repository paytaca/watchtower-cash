import json
import requests
import logging
from rest_framework import serializers
from main.utils import paymentrequest_pb2 as prpb

ca_path = requests.certs.where()
ACK_HEADERS = {'Content-Type':'application/bitcoincash-payment','Accept':'application/bitcoincash-paymentack' }

LOGGER = logging.getLogger("main")

class PaySerializer(serializers.Serializer):
    payment_url = serializers.CharField()
    raw_tx_hex = serializers.CharField()
    source = serializers.CharField(required=False)

    def construct(self):
        payment_pb = prpb.Payment()
        payment_pb.transactions.append(bytes.fromhex(self.validated_data["raw_tx_hex"]))
        self.serialized_payment = payment_pb.SerializeToString()
        
        source = self.validated_data.get("source", None)
        if source == "anypay":
            tx_hex = self.validated_data["raw_tx_hex"]
            self.serialized_payment = json.dumps({
                "chain": "BCH",
                "currency": "BCH",
                "transactions": [{
                    "tx": tx_hex,
                    "weightedSize": int(len(tx_hex) / 2),
                }]
            })
        return self.serialized_payment

    def get_headers(self):
        source = self.validated_data.get("source", None)
        if source == "anypay":
            return { "Content-Type": "application/payment" }
        return ACK_HEADERS

    def send(self):
        try:
            r = requests.post(
                self.validated_data["payment_url"],
                data=self.serialized_payment,
                headers=self.get_headers(),
                verify=ca_path
            )
        except requests.exceptions.RequestException as e:
            LOGGER.error(f"Payment request exception: {e}")
            return False, str(e)

        if r.status_code != 200:
            # Propagate 'Bad request' (HTTP 400) messages to the user since they
            # contain valuable information.
            if r.status_code == 400:
                LOGGER.error(f"Payment request bad request: {r.reason}")
                return False, (r.reason + ": " + r.content.decode('UTF-8'))
            # Some other errors might display an entire HTML document.
            # Hide those and just display the name of the error code.
            LOGGER.error(f"Payment request api error: {r.reason}")
            return False, r.reason

        try:
            response_data = r.json()
            if "memo" in response_data:
                response_data = response_data["memo"]
            LOGGER.info("Payment response: %s" % response_data)
            return True, response_data
        except (json.JSONDecodeError, TypeError):
            pass

        try:
            payment_ack_pb = prpb.PaymentACK()
            payment_ack_pb.ParseFromString(r.content)
        except Exception:
            return False, "PaymentACK could not be processed. Payment was sent; please manually verify that payment was received."
        LOGGER.info("PaymentACK message received: %s" % payment_ack_pb.memo)
        return True, payment_ack_pb.memo


class OutputSerializer(serializers.Serializer):
    address = serializers.CharField()
    amount = serializers.IntegerField()

class PaymentDetailsSerializer(serializers.Serializer):
    payment_id = serializers.CharField(required=False)
    network = serializers.CharField()
    outputs = OutputSerializer(many=True)
    memo = serializers.CharField()
    payment_url = serializers.CharField()

    time = serializers.DateTimeField()
    expires = serializers.DateTimeField()
