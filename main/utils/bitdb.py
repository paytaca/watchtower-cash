import json,requests,base64

class BitDB(object):

    def __init__(self):
        self.base_url = 'https://bitdb.fountainhead.cash/q/'

    def get_data(self, query):
        json_string = bytes(json.dumps(query), 'utf-8')
        url = base64.b64encode(json_string)
        resp = requests.get(f"{self.base_url}{url.decode('utf-8')}")
        data = resp.json()
        return data['c']

    def get_transactions_by_blk(self, blk):
        query = {
            "v": 3,
            "q": {
                "db": ["c"],
                "find": {
                    "blk.i": blk
                },
                "limit": 999999
            }
        }
        return self.get_data(query)

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