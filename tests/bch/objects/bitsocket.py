from django.conf import settings
import json, requests
from main import tasks
from main.models import BlockHeight
import requests_mock

import pytest
import requests


class BitCoinCashTrackerTest(object):	

    def __init__(self, requests_mock, capsys, blockheight_id):
        self.blockheight = BlockHeight.objects.get(id=blockheight_id)
        self.requests_mock = requests_mock
        self.capsys = capsys
        self.url_1 = f"https://rest.bitcoin.com/v2/block/detailsByHeight/{self.blockheight.number}"
        self.url_2 = "https://rest.bitcoin.com/v2/transaction/details/5d4390fac57f8695603320beac63e64d7c295e0191ff4e5eeb9495b829b43ff9"
        data_1 = {
            "hash":"00000000000000000281397ef2d67fe50693ad945c3ece972428695824c1f75a",
            "size":30831,
            "height":648741,
            "version":541065216,
            "merkleroot":"136242297821c75eccab14c4812e79f5865a84d07687c97ba6ce29bf1e9c71cc",
            "tx": ["5d4390fac57f8695603320beac63e64d7c295e0191ff4e5eeb9495b829b43ff9"],
            "time":1597656406,
            "nonce":3760704038,
            "bits":"1802ab52",
            "difficulty":411916163758.6472,
            "chainwork":"0000000000000000000000000000000000000000014306af92a578ab908e29bd",
            "confirmations":1,
            "previousblockhash":"00000000000000000280f1c0ff580fc176716b72012c7dddaad30e1c9d606a55",
            "reward":6.25,
            "isMainChain":True,
            "poolInfo": {
                "poolName":"AntPool",
                "url":"https://antpool.com/"
            }
        }

        data_2 = {
            "txid":"5d4390fac57f8695603320beac63e64d7c295e0191ff4e5eeb9495b829b43ff9",
            "version":2,
            "locktime":0,
            "vin":[
                {
                    "txid":"9d1dc32ae9a3a444a86251377494d0d7da6985e160b26ee6487d3e5885cca7dc",
                    "vout":10,
                    "sequence":4294967295,
                    "n":0,
                    "scriptSig":{
                        "hex":"483045022100dfdff0ffe0d8665b03f039fbee8db20bcfb0fb64e2ff88f560ec18551929fe9f0220156f7da199ca5d3f3dc33498fe8aaf7589abd73f1c7222daf8fba6f0c4c57308412103abc50c026ab54563484dcc02c631e1e336ea1e0700ed85c1a8cbe07304af7fb1",
                        "asm":"3045022100dfdff0ffe0d8665b03f039fbee8db20bcfb0fb64e2ff88f560ec18551929fe9f0220156f7da199ca5d3f3dc33498fe8aaf7589abd73f1c7222daf8fba6f0c4c5730841 03abc50c026ab54563484dcc02c631e1e336ea1e0700ed85c1a8cbe07304af7fb1"
                    },
                    "value":1635226,
                    "legacyAddress":"1D5HkQs9UxSmibJZncZX4cxcgF8EXU41Uj",
                    "cashAddress":"bitcoincash:qzz8zfmh7terygrw8gnyvcvj9x2tu4qzzyw93uvrz6"
                }],
            "vout":[
                {
                    "value":"0.00163742",
                    "n":0,
                    "scriptPubKey":{
                        "hex":"76a91471f92ee31d8376818b90d856156e5356a1738dbe88ac",
                        "asm":"OP_DUP OP_HASH160 71f92ee31d8376818b90d856156e5356a1738dbe OP_EQUALVERIFY OP_CHECKSIG",
                        "addresses":["1BPdsE6i8Xg3b2xHVEc5g2LSzkMnqZvAnn"],
                        "type":"pubkeyhash",
                        "cashAddrs":["bitcoincash:qpcljthrrkphdqvtjrv9v9tw2dt2zuudhcnl444pqa"]
                    },
                    "spentTxId":None,
                    "spentIndex":None,
                    "spentHeight":None
                    },
                {
                    "value":"0.01471218",
                    "n":1,
                    "scriptPubKey":{
                        "hex":"76a91418e03ae1e2ba411a94bcac902af46d6bcc4216b088ac",
                        "asm":"OP_DUP OP_HASH160 18e03ae1e2ba411a94bcac902af46d6bcc4216b0 OP_EQUALVERIFY OP_CHECKSIG",
                        "addresses":["13GXqNvwcz9ofUWEMQReRa5x9Dg1j74iPn"],
                        "type":"pubkeyhash",
                        "cashAddrs":[
                            "bitcoincash:qqvwqwhpu2ayzx55hjkfq2h5d44ucsskkqwfgvrhjw"]
                    },
                    "spentTxId":None,
                    "spentIndex":None,
                    "spentHeight":None
                }
            ],
            "blockhash":"00000000000000000197b0be3d5d44e356b3aa8c0ced3d2c23058a79638ff197",
            "blockheight":648694,
            "confirmations":49,
            "time":1597636367,
            "blocktime":1597636367,
            "firstSeenTime":1597634709,
            "valueOut":0.0163496,
            "size":226,
            "valueIn":0.01635226,
            "fees":0.00000266
        }
        self.expectation_1 = json.dumps(data_1)
        self.expectation_2 = json.dumps(data_2)
        self.output = "('bch', 'bitcoincash:qpcljthrrkphdqvtjrv9v9tw2dt2zuudhcnl444pqa', '5d4390fac57f8695603320beac63e64d7c295e0191ff4e5eeb9495b829b43ff9', '0.00163742', 'alt-bch-tracker', 1, None)\n('bch', 'bitcoincash:qqvwqwhpu2ayzx55hjkfq2h5d44ucsskkqwfgvrhjw', '5d4390fac57f8695603320beac63e64d7c295e0191ff4e5eeb9495b829b43ff9', '0.01471218', 'alt-bch-tracker', 1, None)\n"
    
    def test(self):
        self.requests_mock.get(self.url_1, text=self.expectation_1)
        self.requests_mock.get(self.url_2, text=self.expectation_2)
        tasks.bitcoincash_tracker(id=self.blockheight.id)
        captured = self.capsys.readouterr()
        assert captured.out == self.output
        