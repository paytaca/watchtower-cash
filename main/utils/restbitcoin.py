import requests, json
from main.models import Token

class RestBitcoin(object):

    def __init__(self):
        self.main_url = 'https://rest.bitcoin.com/v2'

    def get_transaction(self, txn_id, blockheightid, currentcount):
        response = {}
        args = ()
        message = status = 'failed'
        transaction_url = f'{self.main_url}/slp/txDetails/{txn_id}'
        proceed = True
        try:
            transaction_response = requests.get(transaction_url)
        except Exception as exc:
            proceed = False
        if proceed == True:
            if transaction_response.status_code == 200:
                try:
                    transaction_data = json.loads(transaction_response.text)
                except Exception as exc:
                    transaction_data = {}
                if 'tokenInfo' in transaction_data.keys():
                    if transaction_data['tokenInfo']:
                        if 'tokenIsValid' in transaction_data['tokenInfo'].keys():
                            if transaction_data['tokenInfo']['tokenIsValid']:
                                if transaction_data['tokenInfo']['transactionType'].lower() in ['send', 'mint', 'burn']:
                                    transaction_token_id = transaction_data['tokenInfo']['tokenIdHex']
                                    token_obj, _ = Token.objects.get_or_create(tokenid=transaction_token_id)
                                    
                                    send_outputs = transaction_data['tokenInfo']['sendOutputs']
                                    # the last index is intended to sender's current balance so we'll going to remove it in send_ouputs.
                                    send_outputs.pop(-1)
                                    spent_index = 1
                                    for output in send_outputs:
                                            amount = float(output)
                                                                            
                                            for legacy in transaction_data['retData']['vout'][spent_index]['scriptPubKey']['addresses']:
                                                """ 
                                                    Since there's no specification for slp addresses, we'll use legacy address that was 
                                                    mapped in every send ouputs.
                                                """
                                                try:
                                                    address_url = 'https://rest.bitcoin.com/v2/address/details/%s' % legacy
                                                    address_response = requests.get(address_url)
                                                    address_data = json.loads(address_response.text)
                                                except Exception as exc:
                                                    # Once fail in sending request, we'll store given params to
                                                    # redis temporarily and retry after 30 minutes cooldown.
                                                    # msg = f'---> FOUND this error {exc} --> Now Delaying...'
                                                    # LOGGER.error(msg)
                                                    proceed = False

                                                if (not 'error' in address_data.keys()) and proceed == True:
                                                    args = (
                                                        token_obj.tokenid,
                                                        address_data['slpAddress'],
                                                        txn_id,
                                                        amount,
                                                        "per-blockheight",
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
                        # Transaction with no token is a BCH transaction and have to be scanned.
                        status = 'success'
                        message = 'no token'

            elif transaction_response.status_code == 404:
                message = 'not found'
                status = 'success'
                            
        # if currentcount == total_transactions:
            
        #     obj = BlockHeight.objects.get(id=blockheightid)
        #     obj.processed=True
        #     obj.save()
        if status == 'failed':
            pass
            # Once error found, we'll saved its params to
            # redis temporarily and resume it after 2 minutes cooldown.
            # msg = f'!!! Error found !!! Suspending to redis...'
            # LOGGER.error(msg)
            # suspendtoredis.delay(txn_id, blockheightid, currentcount, total_transactions)
        response = {
            'status': status,
            'args': args,
            'message': message
        }
        return response