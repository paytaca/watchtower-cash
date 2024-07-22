from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from vouchers.js.runner import ScriptFunctions
from paytacapos.models import Merchant

from bitcash.keygen import public_key_to_address


class Command(BaseCommand):
    help = "Refund accidentally sent BCH from vault contract to the sender"

    def add_arguments(self, parser):
        parser.add_argument("-mid", "--merchant_id", type=int, default=0)
        parser.add_argument("-ra", "--refund_amount", type=int, default=0)
        parser.add_argument("-sa", "--sender_address", type=str, default='')
        parser.add_argument("-spk", "--sender_pubkey", type=str, default='')

    def handle(self, *args, **options):
        merchant_id = options['merchant_id']
        refund_amount = options['refund_amount']
        sender_address = options['sender_address']
        sender_pubkey = options['sender_pubkey']

        address = bytearray.fromhex(sender_pubkey)
        address = public_key_to_address(address)
        
        self.stdout.write(self.style.SUCCESS(address))

        merchant = Merchant.objects.get(id=merchant_id)
        transaction = ScriptFunctions.emergencyRefund(dict(
            params=dict(
                merchant={
                    'receiverPk': merchant.receiving_pubkey
                },
                sender={
                    'pubkey': sender_pubkey,
                    'address': sender_address
                },
                refundAmount=refund_amount
            ),
            options=dict(network=settings.BCH_NETWORK)
        ))

        if transaction:
            txid = transaction['txid']
            self.stdout.write(self.style.SUCCESS(f'Refunded {refund_amount} BCH to {sender_address} from vault contract!')) 
            self.stdout.write(self.style.SUCCESS(f'TXID: {txid}')) 
