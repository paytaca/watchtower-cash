import json
import requests
import base64
import random
import time
import logging

logger = logging.getLogger(__name__)

class BitDBHttpException(Exception):
    pass

class BitDB(object):

    def __init__(self):
        urls = [
            'https://bitdb.fountainhead.cash/q/',
            'https://bitdb2.fountainhead.cash/q/'
        ]
        self.base_url = random.choice(urls)

    def get_data(self, query):
        json_string = bytes(json.dumps(query), 'utf-8')
        url = base64.b64encode(json_string)
        try:
            resp = requests.get(f"{self.base_url}{url.decode('utf-8')}")
        except ConnectionResetError:
            raise BitDBHttpException('Non-200 status')
            
        if resp.status_code == 200:
            data = resp.json()
            return data['c']
        else:
            raise BitDBHttpException('Non-200 status')


    def get_utxos(self, bch_address):
        outputs = [x['tx'] for x in self.get_out(bch_address)]

        chunk = 50
        start = 0
        end = 50
        _round = round(len(outputs)/chunk)
        utxos = []
        spent = []
        while _round >= 0:
            query = {
                "v": 3,
                "q": {
                    "find": {
                        "in.e.h": { 
                            "$in": outputs[start:end]
                        },
                        "in.e.a": bch_address
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
        

    def get_out(self, bch_address):
        query = {
            "v": 3,
            "q": {
                "find": {
                
                "out.e.a": bch_address
                },
                "limit": 999999
            },
            "r": {
                "f": "[.[] | { tx : .tx.h} ]"
            }
        }
        data = self.get_data(query)
        return data

    def get_balance(self, utxos, address):
        value = 0
        for txid in utxos:
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
            logger.error(data[0]['out'])
            logger.error("========")
            # for out in data[0]['out']:
            #     print(out['e'])
            #     if 'a' in out['e'].keys():
            #         if out['e']['a'] == address:
            #             value += out['e']['v'] / (10 ** 8)
        return value

    def get_transactions_count(self, blk):
        query = {
            "v": 3,
            "q": {
                "db": ["c"],
                "find": {
                    "blk.i": blk
                },
                "limit": 999999
            },
            "r": {
                "f": "[.[] | { id : ._id} ]"
            }
        }

        base_count = len(self.get_data(query))
        while True:
            time.sleep(30)
            count = len(self.get_data(query))
            if count == base_count:
                break
            else:
                base_count = count
        return base_count


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
    
    

    def get_transactions_by_blk(self, blk, skip, limit):
        complete = False
        query = {
            "v": 3,
            "q": {
                "db": ["c"],
                "find": {
                    "blk.i": blk
                },
                "skip": skip,
                "limit": limit
            }
        }

        base_count = len(self.get_data(query))
        while True:
            time.sleep(3)
            count = len(self.get_data(query))
            if count == base_count:
                break
            else:
                base_count = count
        if base_count < limit:
            complete = True
        return complete, self.get_data(query)

    def get_latest_block(self):
        query = {
            'v': 3,
            'q': {
                'db': ['c'],
                'aggregate': [
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
                ],
                'limit': 1,
            },
        }
        data = self.get_data(query)
        return data[0]['blk']['i'] 