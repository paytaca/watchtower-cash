
import json
import requests
import base64
import random
import time

class SLPDBHttpExcetion(Exception):
    pass

class SLPDB(object):

    def __init__(self):
        urls = [
            'https://slpdb.fountainhead.cash/q/',
            'https://slpdb.bitcoin.com/q/'
        ]
        self.base_url = random.choice(urls)

    def get_data(self, payload):
        raw = json.dumps(payload)
        raw = raw.replace(", ", ",")
        json_query = str(base64.b64encode(raw.encode()).decode())
        resp = requests.get(f"{self.base_url}{json_query}")
        if resp.status_code == 200:
            data = resp.json()
            return data['c']
        else:
            raise SLPDBHttpExcetion('Non-200 status error')


    def get_block_by_txid(self, txid):
        query = {
            "v": 3,
            "q": {
                "db": ["c"],
                "find": {
                    "tx.h": txid
                },
                "limit": 1
            }
        }
        data = self.get_data(query)
        return data[0]['blk']['i']
        
    def get_transactions_by_blk(self, block):
        payload = {
            'v': 3,
            'q': {
                "db": ["c"],
                "find": {
                    "blk.i": block
                },
                "limit": 100000
            }
        }

        base_count = len(self.get_data(payload))
        while True:
            time.sleep(3)
            count = len(self.get_data(payload))
            if count == base_count:
                break
            else:
                base_count = count
        return self.get_data(payload)
        

    

    