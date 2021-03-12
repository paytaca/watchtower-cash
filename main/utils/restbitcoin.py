import requests, json
from main.models import Token, BlockHeight

class RestBitcoin(object):

    def __init__(self):
        self.main_url = 'https://rest.bitcoin.com/v2'

    def get_data(self, url):
        resp = requests.get(url)
        if resp.status_code == 200:
            resp_data = json.loads(resp.text)
            return resp_data
        return {}

    def get_block(self, block):
        path = f"/block/detailsByHeight/{block}"
        url = f'{self.main_url}{path}'
        return self.get_data(url)

    def bch_checker(self, txn_id):
        path = f"/transaction/details/{txn_id}"
        url = f'{self.main_url}{path}'
        data = self.get_data(url)
        if 'blockheight' in data.keys():
            blockheight_obj, created = BlockHeight.objects.get_or_create(number=data['blockheight'])
            if 'vout' in data.keys():
                for out in data['vout']:
                    if 'scriptPubKey' in out.keys():
                        if 'cashAddrs' in out['scriptPubKey'].keys():
                            for cashaddr in out['scriptPubKey']['cashAddrs']:
                                if cashaddr.startswith('bitcoincash:'):
                                    return (
                                        'bch',
                                        cashaddr,
                                        data['txid'],
                                        out['value'],
                                        "bch_checker",
                                        blockheight_obj.id,
                                        out['spentIndex'],
                                    )
                                    
                        else:
                            # A transaction has no cash address:
                            return (
                                'bch',
                                'unparsed',
                                data['txid'],
                                out['value'],
                                "bch_checker",
                                blockheight_obj.id,
                                out['spentIndex']
                            )
        return None

    def get_transaction(self, txn_id, blockheightid):
        response = {}
        args = ()
        message = status = 'failed'
        path = f"/slp/txDetails/{txn_id}"
        transaction_url = f'{self.main_url}{path}'
        transaction_data = self.get_data(transaction_url)
        if 'tokenInfo' in transaction_data.keys():
            if transaction_data['tokenInfo']:
                if 'tokenIsValid' in transaction_data['tokenInfo'].keys():
                    if transaction_data['tokenInfo']['tokenIsValid']:
                        if transaction_data['tokenInfo']['transactionType'].lower() in ['send', 'mint', 'burn']:
                            transaction_token_id = transaction_data['tokenInfo']['tokenIdHex']
                            token_obj, _ = Token.objects.get_or_create(tokenid=transaction_token_id)
                            
                            send_outputs = transaction_data['tokenInfo']['sendOutputs']
                            spent_index = 1
                            if len(transaction_data['retData']['vout'][spent_index]['scriptPubKey']['addresses']) > 1:
                                # the last index is intended to sender's current balance so we'll going to remove it in send_ouputs.
                                send_outputs.pop(-1)

                            for output in send_outputs:
                                    amount = float(output)
                                                                    
                                    for legacy in transaction_data['retData']['vout'][spent_index]['scriptPubKey']['addresses']:
                                        """ 
                                            Since there's no specification for slp addresses, we'll use legacy address that was 
                                            mapped in every send ouputs.
                                        """
                                        try:
                                            address_url = '{self.main_url}/address/details/%s' % legacy
                                            address_response = requests.get(address_url)
                                            address_data = json.loads(address_response.text)
                                        except Exception as exc:
                                            proceed = False

                                        if (not 'error' in address_data.keys()) and proceed == True:
                                            args = (
                                                token_obj.tokenid,
                                                address_data['slpAddress'],
                                                txn_id,
                                                amount,
                                                "rest.bitcoin-per-block",
                                                blockheightid,
                                                spent_index
                                            )
                                            message = 'found'
                                            status = 'success'

                                    spent_index += 1
                        else:
                            message = transaction_data['tokenInfo']['transactionType'].lower()
                            status = 'success'

                else:
                    LOGGER.error(f'Transaction {txn_id} was invalidated at rest.bitcoin.com')
            else:
                status = 'success'
                message = 'no token'

        response = {
            'status': status,
            'args': args,
            'message': message
        }
        return response