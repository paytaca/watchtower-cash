
from base64 import b64encode,  b64decode
import json
import requests




class SLPDB(object):

    def __init__(self):
        self.reference = 'eyJ2IjogMywicSI6IHsiZGIiOiBbImMiLCAidSJdLCJmaW5kIjp7IiRxdWVyeSI6eyJzbHAuZGV0YWlsLnRva2VuSWRIZXgiOiAiIiwiYmxrLmkiOiAiIn19LCJsaW1pdCI6IDEwMH0sInIiOiB7ImYiOiAiWy5bXSB8IHsgdHhpZDogLnR4LmgsIHRva2VuRGV0YWlsczogLnNscCwgYmxrOiAuYmxrLmkgfSBdIn19'
        self.base_url = 'https://slpdb.fountainhead.cash/q/'

    def get_recent_slp_transactions(self):
        payload = {
            'v': 3,
            'q': {
                'db': ['c', 'u'],
                'aggregate': [
                {
                    '$match': {
                    'slp.valid': True,
                    'slp.detail.transactionType': 'SEND',
                    },
                },
                {
                    '$sort': {
                    '_id': -1,
                    },
                },
                {
                    '$skip': 0,
                },
                {
                    '$limit': 500,
                },
                {
                    '$lookup': {
                    'from': 'tokens',
                    'localField': 'slp.detail.tokenIdHex',
                    'foreignField': 'tokenDetails.tokenIdHex',
                    'as': 'token',
                    },
                },
                ],
                'limit': 500,
            },
        }
        raw = json.dumps(payload)
        raw = raw.replace(", ", ",")
        return str(b64encode(raw.encode()).decode())

    def get_slp_transactions_from_block(self, **kw):
        """
        block : Integer (Optional)
        tokenid : String (Optional)
        """
        data = json.loads(b64decode(self.reference.encode()))
        self.tokenid = kw.get('tokenid', None)
        block = kw.get('block', None)
        if self.tokenid:
            data['q']['find']['$query']['slp.detail.tokenIdHex'] = self.tokenid
        else:
            del data['q']['find']['$query']['slp.detail.tokenIdHex']
        
        if block:
            data['q']['find']['$query']['blk.i'] = block
            if not self.tokenid:
                data['q']['limit'] = 10000
        else:
            del data['q']['find']['$query']['blk.i']
        raw = json.dumps(data)
        raw = raw.replace(", ", ",")
        return str(b64encode(raw.encode()).decode())
    
    def process_api(self):
        data = {'status': 'success'}
        query = self.get_recent_slp_transactions()
        output = requests.get(f'{self.base_url}{query}')
        if output.status_code == 200:
            data['data'] = json.loads(output.text)
        else:
            data['status'] = 'failed'
            data['reason'] = output.reason
        return data