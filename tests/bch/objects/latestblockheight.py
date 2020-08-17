from main import tasks
import json

class LatestBlockHeightTest(object):    

    def __init__(self, requests_mock):
        self.requests_mock = requests_mock
        self.url = f"https://rest.bitcoin.com/v2/blockchain/getBlockchainInfo"
        data = {
            "chain":"main",
            "blocks":648741,
            "headers":648741,
            "bestblockhash":"00000000000000000281397ef2d67fe50693ad945c3ece972428695824c1f75a",
            "difficulty":411916163758.6472,
            "mediantime":1597655159,
            "verificationprogress":0.9999943880587436,
            "initialblockdownload":False,
            "chainwork":"0000000000000000000000000000000000000000014306af92a578ab908e29bd",
            "size_on_disk":169061747744,
            "pruned":False,
            "softforks": {
                "minerfund": {
                    "type":"bip9",
                    "bip9": {
                        "status":"failed",
                        "start_time":1573819200,
                        "timeout":1589544000,
                        "since":637056
                    },"active":False
                },
                "minerfundabc": {
                    "type":"bip9",
                    "bip9": {
                        "status":"failed",
                        "start_time":1573819200,
                        "timeout":1589544000,
                        "since":637056
                    },
                    "active":False
                },
                "minerfundbchd": {
                    "type":"bip9",
                    "bip9": {
                    "status":"failed",
                        "start_time":1573819200,
                        "timeout":1589544000,
                        "since":637056
                    },
                    "active":False
                },
                "minerfundelectroncash": {
                    "type":"bip9",
                    "bip9": {
                        "status":"failed",
                        "start_time":1573819200,
                        "timeout":1589544000,
                        "since":637056
                    },
                    "active":False
                }
            },
            "warnings":"This is a pre-release test build - use at your own risk - do not use for mining or merchant applications"
        }
        self.expectation = json.dumps(data)
        
    
    def test(self):
        self.requests_mock.get(self.url, text=self.expectation)
        tasks.latest_blockheight_getter()