
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


    def get_utxos(self, slp_address):
        outputs = [x['tx'] for x in self.get_out(slp_address)]

        chunk = 50
        start = 0
        end = 50
        _round = round(len(outputs)/chunk)
        
        spent = []
        while _round >= 0:
            query = {
                "v": 3,
                "q": {
                    "find": {
                        "in.e.h": { 
                            "$in": outputs[start:end]
                        },
                        "in.e.a": slp_address
                    },
                    "limit": 9999999
                },
                "r": {
                    "f": "[.[] | { in : .in} ]"
                }
            }
            data = self.get_data(query)
            
            for x in data:
                for i in x['in']:
                    address = i['e']['h']
                    if address in outputs:
                        spent.append(address)

            
            start += chunk    
            end += chunk
            _round -= 1
        
        unspent = [out for out in outputs if out not in spent]
        return list(set(unspent))
    
    def get_out(self, slp_address):
        query = {
            "v": 3,
            "q": {
                "find": {
                    "out.e.a": slp_address
                },
                "limit": 999999
            },
            "r": {
                "f": "[.[] | { tx : .tx.h} ]"
            }
        }
        data = self.get_data(query)
        return data

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
        
        
    def get_transaction(self, tr):
        query = {
            "v": 3,
            "q": {
                "find": {
                        "tx.h": tr
                    },
                "limit": 1
            }
        }
        data = self.get_data(query)
        return data

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
        

    

    