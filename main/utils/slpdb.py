
from base64 import b64encode,  b64decode
import json
import requests

class SLPDB(object):

    def __init__(self):
        self.reference = 'eyJ2IjogMywicSI6IHsiZGIiOiBbImMiLCAidSJdLCJmaW5kIjp7IiRxdWVyeSI6eyJzbHAuZGV0YWlsLnRva2VuSWRIZXgiOiAiIiwiYmxrLmkiOiAiIn19LCJsaW1pdCI6IDEwMH0sInIiOiB7ImYiOiAiWy5bXSB8IHsgdHhpZDogLnR4LmgsIHRva2VuRGV0YWlsczogLnNscCwgYmxrOiAuYmxrLmkgfSBdIn19'
        self.base_url = 'https://slpdb.fountainhead.cash/q/'

    def generate_query(self, **kw):
        """
        block : Integer (Optional)
        tokenid : String (Optional)
        """
        data = json.loads(b64decode(self.reference.encode()))
        tokenid = kw.get('tokenid', None)
        block = kw.get('block', None)
        if tokenid:
            data['q']['find']['$query']['slp.detail.tokenIdHex'] = tokenid
        else:
            del data['q']['find']['$query']['slp.detail.tokenIdHex']
        
        if block:
            data['q']['find']['$query']['blk.i'] = block
            if not tokenid:
                data['q']['limit'] = 10000
        else:
            del data['q']['find']['$query']['blk.i']
        raw = json.dumps(data)
        raw = raw.replace(", ", ",")
        return str(b64encode(raw.encode()).decode())
    
    def process_api(self, **kw):
        data = {'status': 'success'}
        query = self.generate_query(**kw)
        output = requests.get(f'{self.base_url}{query}')
        if output.status_code == 200:
            data['data'] = json.loads(output.text)
        else:
            data['status'] = 'failed'
            data['reason'] = output.reason
        return data