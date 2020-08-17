from django.conf import settings
import json

class BitCoinCashTrackerTest(object):	

    def __init__(self, requests_mock, monkeypatch, capsys):
        self.requests_mock = requests_mock
        self.capsys = capsys

    def test(self):
        expectation = json.dumps([
            {
                'txid': 'ca73c91e626b97001dafe022e0da3c88b6cf976f78f2d1bae73662ad00bdb1d9',
                'tokenDetails': {'valid': True,
                    'detail': {
                        'decimals': 8,
                        'tokenIdHex': '4de69e374a8ed21cbddd47f2338cc0f479dc58daa2bbe11cd604ca488eca0ddf',
                        'transactionType': 'SEND',
                        'versionType': 1,
                        'documentUri': 'spiceslp@gmail.com',
                        'documentSha256Hex': None,
                        'symbol': 'SPICE',
                        'name': 'Spice',
                        'txnBatonVout': None,
                        'txnContainsBaton': False,
                        'outputs': [
                            {
                                'address': 'simpleledger:qrh8c6dmuyx53429hruw2f9c0pc599es0gertxpqlt',
                                'amount': '1000'
                            },
                            {
                                'address': 'simpleledger:qqpwl8vp65hvx5rhjgzxn2fkan8mrm37py3v9qm5vs',
                                'amount': '499995'
                            }
                        ]
                    },
                    'invalidReason': None,
                    'schema_version': 71
                }
            }
        ])
        print('aw')
        return self.capsys.readouterr()
        # qs = User.objects.filter(telegram_id=123)
        # user = qs.first()
        # spice_addr = user.simple_ledger_address
        # token_id = settings.SPICE_TOKEN_ID
        # url = f"https://rest.bitcoin.com/v2/slp/transactions/{token_id}/{spice_addr}"
        # self.requests_mock.get(url, text=expectation)
        # user_list = list(qs.values())
        # assert False == Deposit.objects.all().exists()
        # value = tasks.check_deposits(objList=user_list)
        # assert True == Deposit.objects.all().exists()
        # assert value == ['123 - 1,000.00']