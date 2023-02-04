import traceback
import binascii
import requests
import bitcoin
import cashaddress
import urllib.parse
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import padding
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

        if self.data.pki_type != "none":
            self.x509Certs = pb2.X509Certificates()
            self.x509Certs.ParseFromString(self.data.pki_data)
            self.load_certificates()

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

        parsed_payment_url = urllib.parse.urlparse(self.payment_url)
        path = parsed_payment_url.path
        if isinstance(path, bytes):
            path = path.encode()
        tokenized_path = [segment for segment in path.split('/') if segment]
        self.payment_id = tokenized_path[-1]

        self.time = timezone.datetime.fromtimestamp(self.details.time).replace(tzinfo=timezone.pytz.UTC)
        self.expires = timezone.datetime.fromtimestamp(self.details.expires).replace(tzinfo=timezone.pytz.UTC)

    def verify(self):
        if not isinstance(self.data, pb2.PaymentRequest):
            return
        
        if self.data.pki_type == "none":
            return True
        elif self.data.pki_type in ["x509+sha256", "x509+sha1"]:
            try:
                verify_cert_chain()
                return True
            except: 
                return False

    def verify_cert_chain(self):
        certs_num = len(self.certificates)
        cert = self.certificates[0]
        for i in range(1, certs_num):
            next_cert = self.certificates[i]
            cert.public_key().verify(
                next_cert.signature,
                next_cert.tbs_certificate_bytes,
                padding.PKCS1v15(),
                next_cert.signature_hash_algorithm,
            )
            cert = next_cert

    def load_certificates(self):
        if not hasattr(self, "x509Certs") or not isinstance(self.x509Certs, pb2.X509Certificates):
            return

        certificates = []
        for cert in self.x509Certs.certificate:
            certificates.append(
                x509.load_der_x509_certificate(cert, default_backend())
            )
        self.certificates = certificates
        self.certificates.reverse()

        try:
            self.verify_cert_chain()
        except:
            traceback.print_exc()
            self.error = "Encountered error in verifying cert chain"

        return certificates
