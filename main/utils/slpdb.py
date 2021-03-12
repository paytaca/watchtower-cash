
from base64 import b64encode,  b64decode
import json
import requests

class SLPDB(object):

    def __init__(self):
        self.base_url = 'https://slpdb.fountainhead.cash/q/'

    def get_data(self, json_string):
        url = base64.b64encode(json_string)
        resp = requests.get(f"{self.base_url}{url.decode('utf-8')}")
        data = resp.json()
        return data['c']

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
        raw = json.dumps(payload)
        raw = raw.replace(", ", ",")
        json_string = str(b64encode(raw.encode()).decode())
        self.get_data(json_string)

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
        json_query = str(b64encode(raw.encode()).decode())
        self.get_data(json_query)
    