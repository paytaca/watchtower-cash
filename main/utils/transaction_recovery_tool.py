
from main.models import BlockHeight, Transaction
from main.tasks import save_record
import requests, json

class TRT(object):
    
    def bchaddress_scanner(self, bchaddress):
        addresses = [bchaddress]
        source = 'bch-address-scanner'
        url = 'https://rest.bitcoin.com/v2/address/transactions'
        data = { "addresses": addresses}
        resp = requests.post(url, json=data)
        data = json.loads(resp.text)
        for row in data:
            for tr in row['txs']:
                blockheight, created = BlockHeight.objects.get_or_create(number=tr['blockheight'])
                for out in tr['vout']:
                    amount = out['value']
                    spent_index = tr['vout'][0]['spentIndex'] or 0
                    if 'addresses' in out['scriptPubKey'].keys():
                        for legacy in out['scriptPubKey']['addresses']:
                            address_url = 'https://rest.bitcoin.com/v2/address/details/%s' % legacy
                            address_response = requests.get(address_url)
                            address_data = json.loads(address_response.text)
                            args = (
                                'bch',
                                address_data['cashAddress'],
                                tr['txid'],
                                out['value'],
                                source,
                                blockheight.id,
                                spent_index
                            )
                            if not Transaction.objects.filter(txid=tr['txid']).exists():
                                save_record(*args)

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