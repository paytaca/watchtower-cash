from django.conf import settings
import json, requests
from main import tasks
import requests_mock
import pytest
import requests


class BitSocketTest(object):	

    def __init__(self, requests_mock, capsys):
        self.requests_mock = requests_mock
        self.capsys = capsys
        self.url_1 = f"https://bitsocket.bch.sx/s/ewogICJ2IjogMywKICAicSI6IHsKICAgICJmaW5kIjoge30KICB9Cn0="
        data_1 = {"type":"mempool","data":[{"tx":{"h":"34c1ace1e633a068cc2da375f96b602af2d0214ccd935808c6dda9afba236cd3"},"in":[{"i":0,"b0":"MEQCIEt2la/y62aup6NkaHDKtOVtR5nLwVKfn+C05sDfD7MYAiAkJ/DnssV9C19UjueBSq5Mm/g6MtdJQ1xuA5XxqkrXIUE=","b1":"AijVj2zqYkWD+J+kEQgmblGPPAaeKwDZRqQVz/OkSN+R","str":"304402204b7695aff2eb66aea7a3646870cab4e56d4799cbc1529f9fe0b4e6c0df0fb31802202427f0e7b2c57d0b5f548ee7814aae4c9bf83a32d749435c6e0395f1aa4ad72141 0228d58f6cea624583f89fa41108266e518f3c069e2b00d946a415cff3a448df91","e":{"h":"5cf73888c00d7b2813443ddb2662408dcc14a7d53e84e28feb1aadae3a7066ae","i":1,"a":"qqsr4pnqwwqs7xd0gquaxl7jntdu7k2ercj4pqe5jc"},"h0":"304402204b7695aff2eb66aea7a3646870cab4e56d4799cbc1529f9fe0b4e6c0df0fb31802202427f0e7b2c57d0b5f548ee7814aae4c9bf83a32d749435c6e0395f1aa4ad72141","h1":"0228d58f6cea624583f89fa41108266e518f3c069e2b00d946a415cff3a448df91"},{"i":1,"b0":"MEUCIQDdmAveKZiqbd+bGn16fLcH2dEzYcNC/3M5ZeJnrRCRqgIgCmiSA+NU/ogPxF/m9Sy4C9GYMj6Q6aJ4NOCq3Y7swepB","b1":"AijVj2zqYkWD+J+kEQgmblGPPAaeKwDZRqQVz/OkSN+R","str":"3045022100dd980bde2998aa6ddf9b1a7d7a7cb707d9d13361c342ff733965e267ad1091aa02200a689203e354fe880fc45fe6f52cb80bd198323e90e9a27834e0aadd8eecc1ea41 0228d58f6cea624583f89fa41108266e518f3c069e2b00d946a415cff3a448df91","e":{"h":"974843206a69d7de2eb4a3fd1509edca173a2fb0420879a8dff7f57f0a068b9c","i":1,"a":"qqsr4pnqwwqs7xd0gquaxl7jntdu7k2ercj4pqe5jc"},"h0":"3045022100dd980bde2998aa6ddf9b1a7d7a7cb707d9d13361c342ff733965e267ad1091aa02200a689203e354fe880fc45fe6f52cb80bd198323e90e9a27834e0aadd8eecc1ea41","h1":"0228d58f6cea624583f89fa41108266e518f3c069e2b00d946a415cff3a448df91"}],"out":[{"i":0,"b0":{"op":106},"b1":"U0xQAA==","s1":"SLP\u0000","b2":"AQ==","s2":"\u0001","b3":"U0VORA==","s3":"SEND","b4":"ZEg4H5ZJ7KzYwwGJz7/ucakba5c46klP4z+Li1HL/KA=","s4":"dH8\u001fï¿½Iï¿½ï¿½ï¿½\u0001ï¿½Ï¿ï¿½qï¿½\u001bkï¿½8ï¿½IOï¿½?ï¿½ï¿½Qï¿½ï¿½ï¿½","b5":"AAAAASoF8gA=","s5":"\u0000\u0000\u0000\u0001*\u0005ï¿½\u0000","str":"OP_RETURN 534c5000 01 53454e44 6448381f9649ecacd8c30189cfbfee71a91b6b9738ea494fe33f8b8b51cbfca0 000000012a05f200","e":{"v":0,"i":0},"h1":"534c5000","h2":"01","h3":"53454e44","h4":"6448381f9649ecacd8c30189cfbfee71a91b6b9738ea494fe33f8b8b51cbfca0","h5":"000000012a05f200"},{"i":1,"b0":{"op":118},"b1":{"op":169},"b2":"IDqGYHOBDxmvQDnTf9Ka289ZWR4=","s2":" :ï¿½`sï¿½\u000f\u0019ï¿½@9ï¿½Òšï¿½ï¿½YY\u001e","b3":{"op":136},"b4":{"op":172},"str":"OP_DUP OP_HASH160 203a866073810f19af4039d37fd29adbcf59591e OP_EQUALVERIFY OP_CHECKSIG","e":{"v":546,"i":1,"a":"qqsr4pnqwwqs7xd0gquaxl7jntdu7k2ercj4pqe5jc"},"h2":"203a866073810f19af4039d37fd29adbcf59591e"},{"i":2,"b0":{"op":118},"b1":{"op":169},"b2":"IDqGYHOBDxmvQDnTf9Ka289ZWR4=","s2":" :ï¿½`sï¿½\u000f\u0019ï¿½@9ï¿½Òšï¿½ï¿½YY\u001e","b3":{"op":136},"b4":{"op":172},"str":"OP_DUP OP_HASH160 203a866073810f19af4039d37fd29adbcf59591e OP_EQUALVERIFY OP_CHECKSIG","e":{"v":1277062,"i":2,"a":"qqsr4pnqwwqs7xd0gquaxl7jntdu7k2ercj4pqe5jc"},"h2":"203a866073810f19af4039d37fd29adbcf59591e"}],"_id":"5f3b850d05aea9511495d145"}]}
        self.expectation_1 = json.dumps(data_1)
        self.output = "('bch', 'bitcoincash:qpcljthrrkphdqvtjrv9v9tw2dt2zuudhcnl444pqa', '5d4390fac57f8695603320beac63e64d7c295e0191ff4e5eeb9495b829b43ff9', '0.00163742', 'alt-bch-tracker', 1, None)\n('bch', 'bitcoincash:qqvwqwhpu2ayzx55hjkfq2h5d44ucsskkqwfgvrhjw', '5d4390fac57f8695603320beac63e64d7c295e0191ff4e5eeb9495b829b43ff9', '0.01471218', 'alt-bch-tracker', 1, None)\n"
        # Back into this once all tests are set
        self.output = ''
    
    def test(self):
        self.requests_mock.get(self.url_1, text=self.expectation_1)
        tasks.bitsocket()
        captured = self.capsys.readouterr()
        assert captured.out == self.output
        