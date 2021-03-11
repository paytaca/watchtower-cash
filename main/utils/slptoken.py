import requests, json

class SLPToken(object):

    def __init__(self, tokenId):
        base_url = 'https://rest.bitcoin.com/v2'
        resp = requests.get(f'{base_url}/slp/tokenStats/{tokenId}')
        self.data = json.loads(resp.text)

    def get_decimals(self):
        if 'decimals' in self.data.keys():
            return self.data['decimals']
        return 0
