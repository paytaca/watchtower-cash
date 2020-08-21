from django.conf import settings
import json, requests
from main import tasks
import requests_mock
import pytest
import requests


class SLPDBTokenScannerTest(object):	

    def __init__(self, requests_mock, capsys):
        self.url_1 = 'https://slpdb.fountainhead.cash/q/eyJ2IjogMywicSI6IHsiZGIiOiBbImMiLCJ1Il0sImZpbmQiOiB7IiRxdWVyeSI6IHsic2xwLmRldGFpbC50b2tlbklkSGV4IjogIjRkZTY5ZTM3NGE4ZWQyMWNiZGRkNDdmMjMzOGNjMGY0NzlkYzU4ZGFhMmJiZTExY2Q2MDRjYTQ4OGVjYTBkZGYifX0sImxpbWl0IjogMTAwfSwiciI6IHsiZiI6ICJbLltdIHwgeyB0eGlkOiAudHguaCx0b2tlbkRldGFpbHM6IC5zbHAsYmxrOiAuYmxrLmkgfSBdIn19'
        self.url_2 = 'https://slpdb.fountainhead.cash/q/eyJ2IjogMywicSI6IHsiZGIiOiBbImMiLCJ1Il0sImZpbmQiOiB7IiRxdWVyeSI6IHt9fSwibGltaXQiOiAxMDB9LCJyIjogeyJmIjogIlsuW10gfCB7IHR4aWQ6IC50eC5oLHRva2VuRGV0YWlsczogLnNscCxibGs6IC5ibGsuaSB9IF0ifX0='
        self.url_3 = 'https://slpdb.fountainhead.cash/q/eyJ2IjogMywicSI6IHsiZGIiOiBbImMiLCJ1Il0sImZpbmQiOiB7IiRxdWVyeSI6IHsic2xwLmRldGFpbC50b2tlbklkSGV4IjogImQ2ODc2ZjBmY2U2MDNiZTQzZjE1ZDM0MzQ4YmIxZGUxYThkNjg4ZTExNTI1OTY1NDNkYTAzM2EwNjBjZmY3OTgifX0sImxpbWl0IjogMTAwfSwiciI6IHsiZiI6ICJbLltdIHwgeyB0eGlkOiAudHguaCx0b2tlbkRldGFpbHM6IC5zbHAsYmxrOiAuYmxrLmkgfSBdIn19'
        self.url_4 = 'https://slpdb.fountainhead.cash/q/eyJ2IjogMywicSI6IHsiZGIiOiBbImMiLCJ1Il0sImZpbmQiOiB7IiRxdWVyeSI6IHsic2xwLmRldGFpbC50b2tlbklkSGV4IjogIjBmM2YyMjM5MDJjNDRkYzJiZWU2ZDNmNzdkNTY1OTA0ZDg1MDFhZmZiYTVlZTBjNTZmN2IzMmU4MDgwY2UxNGIifX0sImxpbWl0IjogMTAwfSwiciI6IHsiZiI6ICJbLltdIHwgeyB0eGlkOiAudHguaCx0b2tlbkRldGFpbHM6IC5zbHAsYmxrOiAuYmxrLmkgfSBdIn19'
        self.expectation_1 = json.dumps({"c":[
            {
                "txid":"4b221151674cafc4ed4e6a1e10a16747ebbfc741e0bbe5ccb37d83c0bd073801",
                "tokenDetails":{
                    "valid":True,
                    "detail":{
                        "decimals":8,
                        "tokenIdHex":"4de69e374a8ed21cbddd47f2338cc0f479dc58daa2bbe11cd604ca488eca0ddf",
                        "transactionType":"SEND","versionType":1,"documentUri":"spiceslp@gmail.com","documentSha256Hex":None,"symbol":"SPICE","name":"Spice","txnBatonVout":None,"txnContainsBaton":False,
                        "outputs":[{"address":"simpleledger:qzlpghvxfpu5zqmdwtlqd5gwpypk4gsyxyqf9rj5u8","amount":"795"},
                        {"address":"simpleledger:qpzer6qyapt7a5jpzh64hpr0ax509vh73yrt8ujhdr","amount":"0.37701135"}]},
                        "invalidReason":None,"schema_version":79},"blk":649291
            }
            ],"u":[]
        })
        self.expectation_2 = json.dumps({"c":[
            {
                "txid":"4b221151674cafc4ed4e6a1e10a16747ebbfc741e0bbe5ccb37d83c0bd073802",
                "tokenDetails":{
                    "valid":True,
                    "detail":{
                        "decimals":8,
                        "tokenIdHex":"",
                        "transactionType":"SEND","versionType":1,"documentUri":"spiceslp@gmail.com","documentSha256Hex":None,"symbol":"SPICE","name":"Spice","txnBatonVout":None,"txnContainsBaton":False,
                        "outputs":[{"address":"simpleledger:qzlpghvxfpu5zqmdwtlqd5gwpypk4gsyxyqf9rj5u8","amount":"795"},
                        {"address":"simpleledger:qpzer6qyapt7a5jpzh64hpr0ax509vh73yrt8ujhdr","amount":"0.37701135"}]},
                        "invalidReason":None,"schema_version":79},"blk":649291
            }
            ],"u":[]
        })
        self.expectation_3 = json.dumps({"c":[
            {
                "txid":"4b221151674cafc4ed4e6a1e10a16747ebbfc741e0bbe5ccb37d83c0bd073803",
                "tokenDetails":{
                    "valid":True,
                    "detail":{
                        "decimals":8,
                        "tokenIdHex":"d6876f0fce603be43f15d34348bb1de1a8d688e1152596543da033a060cff798",
                        "transactionType":"SEND","versionType":1,"documentUri":"spiceslp@gmail.com","documentSha256Hex":None,"symbol":"SPICE","name":"Spice","txnBatonVout":None,"txnContainsBaton":False,
                        "outputs":[{"address":"simpleledger:qzlpghvxfpu5zqmdwtlqd5gwpypk4gsyxyqf9rj5u8","amount":"795"},
                        {"address":"simpleledger:qpzer6qyapt7a5jpzh64hpr0ax509vh73yrt8ujhdr","amount":"0.37701135"}]},
                        "invalidReason":None,"schema_version":79},"blk":649291
            }
            ],"u":[]
        })
        self.expectation_4 = json.dumps({"c":[
            {
                "txid":"4b221151674cafc4ed4e6a1e10a16747ebbfc741e0bbe5ccb37d83c0bd073804",
                "tokenDetails":{
                    "valid":True,
                    "detail":{
                        "decimals":8,
                        "tokenIdHex":"0f3f223902c44dc2bee6d3f77d565904d8501affba5ee0c56f7b32e8080ce14b",
                        "transactionType":"SEND","versionType":1,"documentUri":"spiceslp@gmail.com","documentSha256Hex":None,"symbol":"SPICE","name":"Spice","txnBatonVout":None,"txnContainsBaton":False,
                        "outputs":[{"address":"simpleledger:qzlpghvxfpu5zqmdwtlqd5gwpypk4gsyxyqf9rj5u8","amount":"795"},
                        {"address":"simpleledger:qpzer6qyapt7a5jpzh64hpr0ax509vh73yrt8ujhdr","amount":"0.37701135"}]},
                        "invalidReason":None,"schema_version":79},"blk":649291
            }
            ],"u":[]
        })

        self.output = "('4de69e374a8ed21cbddd47f2338cc0f479dc58daa2bbe11cd604ca488eca0ddf', 'simpleledger:qzlpghvxfpu5zqmdwtlqd5gwpypk4gsyxyqf9rj5u8', '4b221151674cafc4ed4e6a1e10a16747ebbfc741e0bbe5ccb37d83c0bd073801', '795', 'slpdb_token_scanner', 2, 1)\n('', 'simpleledger:qzlpghvxfpu5zqmdwtlqd5gwpypk4gsyxyqf9rj5u8', '4b221151674cafc4ed4e6a1e10a16747ebbfc741e0bbe5ccb37d83c0bd073802', '795', 'slpdb_token_scanner', 2, 1)\n('d6876f0fce603be43f15d34348bb1de1a8d688e1152596543da033a060cff798', 'simpleledger:qzlpghvxfpu5zqmdwtlqd5gwpypk4gsyxyqf9rj5u8', '4b221151674cafc4ed4e6a1e10a16747ebbfc741e0bbe5ccb37d83c0bd073803', '795', 'slpdb_token_scanner', 2, 1)\n('0f3f223902c44dc2bee6d3f77d565904d8501affba5ee0c56f7b32e8080ce14b', 'simpleledger:qzlpghvxfpu5zqmdwtlqd5gwpypk4gsyxyqf9rj5u8', '4b221151674cafc4ed4e6a1e10a16747ebbfc741e0bbe5ccb37d83c0bd073804', '795', 'slpdb_token_scanner', 2, 1)\n"
        self.requests_mock = requests_mock
        self.capsys = capsys
        
    
    def test(self):
        self.requests_mock.get(self.url_1, text=self.expectation_1)
        self.requests_mock.get(self.url_2, text=self.expectation_2)
        self.requests_mock.get(self.url_3, text=self.expectation_3)
        self.requests_mock.get(self.url_4, text=self.expectation_4)
        tasks.slpdb_token_scanner()
        captured = self.capsys.readouterr()
        assert captured.out == self.output
        