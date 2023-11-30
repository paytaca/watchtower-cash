from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import generics
from rest_framework import status
from main import serializers
from main.models import Address
from main.tasks import rescan_utxos
from main.utils.queries.bchn import BCHN
from main.tasks import broadcast_transaction
from main.tasks import process_mempool_transaction_fast


def _get_wallet_hash(tx_hex):
    bchn = BCHN()
    wallet_hash = None
    try:
        tx = bchn._decode_raw_transaction(tx_hex)
        input0 = tx['vin'][0]
        input0_tx = bchn._get_raw_transaction(input0['txid'])
        vout_data = input0_tx['vout'][input0['vout']]
        if vout_data['scriptPubKey']['type'] == 'pubkeyhash':
            address = vout_data['scriptPubKey']['addresses'][0]
            try:
                address_obj = Address.objects.get(address=address)
                if address_obj.wallet:
                    wallet_hash = address_obj.wallet.wallet_hash
            except Address.DoesNotExist:
                pass
    except:
        pass
    return wallet_hash


class BroadcastViewSet(generics.GenericAPIView):
    serializer_class = serializers.BroadcastSerializer
    permission_classes = [AllowAny,]

    def post(self, request, format=None):
        serializer = self.get_serializer(data=request.data)
        response = {'success': False}
        if serializer.is_valid():
            # job = broadcast_transaction.delay(serializer.data['transaction'])
            # success, result = job.get()
            success, result = broadcast_transaction(serializer.data['transaction'])
            if 'already have transaction' in result:
                success = True
            if success:
                txid = result.split(' ')[-1]
                response['txid'] = txid
                response['success'] = True
                process_mempool_transaction_fast(txid, serializer.data['transaction'], True)
                return Response(response, status=status.HTTP_200_OK)
            else:
                # Do a wallet utxo rescan if failed
                wallet_hash = _get_wallet_hash(serializer.data['transaction'])
                rescan_utxos.delay(wallet_hash)

                response['error'] = result + '. [This problem might resolve itself. Try again in a few seconds.]'
                return Response(response, status=status.HTTP_409_CONFLICT)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
