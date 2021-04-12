import json
import requests
import base64
import random
import time

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
            time.sleep(5)
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