
from main.models import BlockHeight, Transaction
from main.tasks import save_record
import requests, json

class TRT(object):
    

    def recover_bch_tx(self, txid, block=None):
        url = f'https://rest.bitcoin.com/v2/transaction/details/{txn_id}'
        response = requests.get(url)
        if response.status_code == 200:
            data = json.loads(response.text)
            if 'vout' in data.keys():
                for out in data['vout']:
                    if 'scriptPubKey' in out.keys():
                        if 'cashAddrs' in out['scriptPubKey'].keys():
                            for cashaddr in out['scriptPubKey']['cashAddrs']:
                                if cashaddr.startswith('bitcoincash:'):
                                    args = (
                                        'bch',
                                        cashaddr,
                                        txn_id,
                                        out['value'],
                                        "alternative-bch-tracker",
                                        block,
                                        out['spentIndex']
                                    )
                                    # Don't delay saving of records.
                                    save_record(*args)
                                        
    def recover_bch_txs_in_block(self,id):
        blockheight_obj= BlockHeight.objects.get(id=id)
        url = f"https://rest.bitcoin.com/v2/block/detailsByHeight/{blockheight_obj.number}"
        try:
            resp = requests.get(url)
            data = json.loads(resp.text)
        except (ConnectionError, json.decoder.JSONDecodeError) as exc:
            return self.retry(countdown=5)
        if 'tx' in data.keys():
            for txn_id in data['tx']:
                trans = Transaction.objects.filter(txid=txn_id)
                if not trans.exists():
                    self.recover_bch_tx(txn_id, blockheight_obj.id)