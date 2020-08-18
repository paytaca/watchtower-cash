from django.conf import settings
import json, requests
from main import tasks
import requests_mock

import pytest
import requests


class BitDBQueryTest(object):    

    def __init__(self, requests_mock, capsys):
        self.requests_mock = requests_mock
        self.capsys = capsys
        self.url_1 = f"https://bitdb.fountainhead.cash/q/eyJ2IjogMywgInEiOiB7ImZpbmQiOiB7fSwgImxpbWl0IjogMTAwMH19"
        data_1 = {
            "u":[
                {
                    "_id":"5f3b453f05aea9511495a2b0",
                    "tx":{
                        "h":"de0847e87c1387b72d02f5942569f3ff5b1ef3c7eafd623fc4d073f9d4436e9c"
                    },
                    "in":[
                        {
                            "i":0,
                            "b0":"MEQCIHaAv6htSN3XaIGKb43SO2Jfg0+Koa0m+F5zqJZHshV7AiAF6ZoWrJKaqd2deuTpnPTiiPQ8Ch/ZUSwA6weP35rlZ0E=",
                            "b1":"AhdFqjK3yrlKWDmXxrFIknA19mBejRUbcEygnR4NDAOB",
                            "str":"304402207680bfa86d48ddd768818a6f8dd23b625f834f8aa1ad26f85e73a89647b2157b022005e99a16ac929aa9dd9d7ae4e99cf4e288f43c0a1fd9512c00eb078fdf9ae56741 021745aa32b7cab94a583997c6b148927035f6605e8d151b704ca09d1e0d0c0381",
                            "e":{
                                "h":"a55e9f76b20a41eefe44d45adf8edc915488d29265a955401359f3d258b250ba",
                                "i":1,
                                "a":"qrqacq79pymulcf505lm09qnpaeg5xg7ns6pggsmd0"
                            },
                            "h0":"304402207680bfa86d48ddd768818a6f8dd23b625f834f8aa1ad26f85e73a89647b2157b022005e99a16ac929aa9dd9d7ae4e99cf4e288f43c0a1fd9512c00eb078fdf9ae56741",
                            "h1":"021745aa32b7cab94a583997c6b148927035f6605e8d151b704ca09d1e0d0c0381"
                        }
                    ],
                    "out":[
                        {
                            "i":0,
                            "b0": {"op":118},
                            "b1":{"op":169},
                            "b2":"4zbaMCGLZlp9iNFqnYmkztStQ+E=",
                            "s2":"�6�0!�fZ}��j����ԭC�",
                            "b3":{"op":136},
                            "b4":{"op":172},
                            "str":"OP_DUP OP_HASH160 e336da30218b665a7d88d16a9d89a4ced4ad43e1 OP_EQUALVERIFY OP_CHECKSIG",
                            "e":{
                                "v":71501830329,
                                "i":0,
                                "a":"qr3ndk3syx9kvkna3rgk48vf5n8dft2ruylpkn54rq"
                            },
                            "h2":"e336da30218b665a7d88d16a9d89a4ced4ad43e1"
                        },
                        {
                            "i":1,
                            "b0":{"op":118},
                            "b1":{"op":169},
                            "b2":"f82F/wSYcpphcGC0ale9pOV0sgE=",
                            "s2":"ͅ�\u0004�r�ap`�jW���t�\u0001",
                            "b3":{"op":136},
                            "b4":{"op":172},
                            "str":"OP_DUP OP_HASH160 7fcd85ff0498729a617060b46a57bda4e574b201 OP_EQUALVERIFY OP_CHECKSIG",
                            "e": {
                                "v":1462212686,
                                "i":1,
                                "a":"qplump0lqjv89xnpwpstg6jhhkjw2a9jqyawg7j0v5"
                            },
                            "h2":"7fcd85ff0498729a617060b46a57bda4e574b201"
                        }
                    ]
                },{
                    "_id":"5f3b453f05aea9511495a2b1",
                    "tx":{
                        "h":"2d2e956f4c32809cf5571f92b38a21a787e0f8bd03ad4f4731b0e0d6fb5a35b7"
                    },
                    "in":[{
                        "i":0,"b0":"MEQCIBm2tz0KBqC1Jj6xqQ//povL/lgVCpi0fWFdiWSzoCSZAiBsSt9opvlj9BcEzIb/JDCqYVJUtiJ4s3H471gUR4Dr2UE=",
                        "b1":"ApmNDZ1qdT3oekjm/HXCL4rBwY0Y7AeWpl6a9ixGuJwZ",
                        "str":"3044022019b6b73d0a06a0b5263eb1a90fffa68bcbfe58150a98b47d615d8964b3a0249902206c4adf68a6f963f41704cc86ff2430aa615254b62278b371f8ef58144780ebd941 02998d0d9d6a753de87a48e6fc75c22f8ac1c18d18ec0796a65e9af62c46b89c19",
                        "e":{
                            "h":"d9445e26a2f190e4f3204a1fed4001b37d750331a3c377e9e55d0f564eddfc02",
                            "i":1,"a":"qq96gx0y8dc3sg5uhlxpmc7gfxdudnsznvc7hmn48h"
                        },
                        "h0":"3044022019b6b73d0a06a0b5263eb1a90fffa68bcbfe58150a98b47d615d8964b3a0249902206c4adf68a6f963f41704cc86ff2430aa615254b62278b371f8ef58144780ebd941",
                        "h1":"02998d0d9d6a753de87a48e6fc75c22f8ac1c18d18ec0796a65e9af62c46b89c19"
                    }],
                    "out":[
                        {
                            "i":0,
                            "b0":{"op":118},
                            "b1":{"op":169},
                            "b2":"Sw/4C4hQq9WQoJTlHu4+qc15XZA=",
                            "s2":"K\u000f�\u000b�P�Ր���\u001e�>��y]�",
                            "b3":{"op":136},
                            "b4":{"op":172},
                            "str":"OP_DUP OP_HASH160 4b0ff80b8850abd590a094e51eee3ea9cd795d90 OP_EQUALVERIFY OP_CHECKSIG",
                            "e":{"v":281649670716,"i":0,"a":"qp9sl7qt3pg2h4vs5z2w28hw865u672ajqtfevzrqr"},
                            "h2":"4b0ff80b8850abd590a094e51eee3ea9cd795d90"
                        },
                        {
                            "i":1,
                            "b0":{"op":118},
                            "b1":{"op":169},
                            "b2":"4+Af2OMcvDGIIx8jtYy7+2DZpeE=",
                            "s2":"��\u001f��\u001c�1�#\u001f#����`٥�",
                            "b3":{"op":136},
                            "b4":{"op":172},
                            "str":"OP_DUP OP_HASH160 e3e01fd8e31cbc3188231f23b58cbbfb60d9a5e1 OP_EQUALVERIFY OP_CHECKSIG",
                            "e":{
                                "v":814000000,
                                "i":1,
                                "a":"qr37q87cuvwtcvvgyv0j8dvvh0akpkd9uyxc8vg70y"
                            },
                            "h2":"e3e01fd8e31cbc3188231f23b58cbbfb60d9a5e1"
                        },
                        {
                            "i":2,
                            "b0":{"op":118},
                            "b1":{"op":169},
                            "b2":"ExB+mw9kSQ9lYaptA9tkDWUIHSM=",
                            "s2":"\u0013\u0010~�\u000fdI\u000fea�m\u0003�d\re\b\u001d#",
                            "b3":{"op":136},
                            "b4":{"op":172},
                            "str":"OP_DUP OP_HASH160 13107e9b0f64490f6561aa6d03db640d65081d23 OP_EQUALVERIFY OP_CHECKSIG",
                            "e":{
                                "v":20960000,
                                "i":2,
                                "a":"qqf3ql5mpajyjrm9vx4x6q7mvsxk2zqayvqj3ntjua"
                            },
                            "h2":"13107e9b0f64490f6561aa6d03db640d65081d23"
                        }
                    ]
                }
            ],
            "c":[
                {
                    "_id":"5f3b44e505aea95114959e02",
                    "tx":{
                        "h":"ff452c928e75cef57716512c805fb2ee5eafbc21da6dc7b778a68955c90572c7"
                    },
                    "in":[
                        {
                            "i":0,
                            "b0":"MEUCIQCOFv6JxhEGtGSQzKGtiuwDJYyWRQWtpONGu+zYMuFPZwIgNEMw4fXEp3Y11xz6/N92lYH2YMlf/F4yB81pWIX/7ZtB",
                            "b1":"A8lXYmR8p+5ZQ7CL14ueUHfhseGwpVbIaW6MtDAAkahU",
                            "str":"30450221008e16fe89c61106b46490cca1ad8aec03258c964505ada4e346bbecd832e14f670220344330e1f5c4a77635d71cfafcdf769581f660c95ffc5e3207cd695885ffed9b41 03c95762647ca7ee5943b08bd78b9e5077e1b1e1b0a556c8696e8cb4300091a854",
                            "e":{
                                "h":"c109bb381a386cabcd0ce019b61f7a0bc1b98892e92362734fc3f989cc05ba2c",
                                "i":2,
                                "a":"qpmqz4sayysnltvkzcjr9qc938qj2y9pyu9hvr7dxg"
                            },
                            "h0":"30450221008e16fe89c61106b46490cca1ad8aec03258c964505ada4e346bbecd832e14f670220344330e1f5c4a77635d71cfafcdf769581f660c95ffc5e3207cd695885ffed9b41",
                            "h1":"03c95762647ca7ee5943b08bd78b9e5077e1b1e1b0a556c8696e8cb4300091a854"
                        },
                        {
                            "i":1,
                            "b0":"MEQCIDjrXd1KuBmzO5lt/JtXWXNePfjDBMMQCNyp7XzpFDMjAiBmptI++5PdiQuVksUtL7at9LAsQX8RKUHTI70xSOSaP0E=",
                            "b1":"A8lXYmR8p+5ZQ7CL14ueUHfhseGwpVbIaW6MtDAAkahU",
                            "str":"3044022038eb5ddd4ab819b33b996dfc9b5759735e3df8c304c31008dca9ed7ce9143323022066a6d23efb93dd890b9592c52d2fb6adf4b02c417f112941d323bd3148e49a3f41 03c95762647ca7ee5943b08bd78b9e5077e1b1e1b0a556c8696e8cb4300091a854",
                            "e":{
                                "h":"5325574b08d2401732949d8c3cfd0bc702f41a2a5aae3dfabca3b16d4b25cf30",
                                "i":2,
                                "a":"qpmqz4sayysnltvkzcjr9qc938qj2y9pyu9hvr7dxg"
                            },
                            "h0":"3044022038eb5ddd4ab819b33b996dfc9b5759735e3df8c304c31008dca9ed7ce9143323022066a6d23efb93dd890b9592c52d2fb6adf4b02c417f112941d323bd3148e49a3f41",
                            "h1":"03c95762647ca7ee5943b08bd78b9e5077e1b1e1b0a556c8696e8cb4300091a854"
                        }
                    ],
                    "out":[
                        {
                            "i":0,
                            "b0":{"op":106},
                            "b1":"U0xQAA==",
                            "s1":"SLP\u0000",
                            "b2":"AQ==",
                            "s2":"\u0001",
                            "b3":"U0VORA==",
                            "s3":"SEND",
                            "b4":"TeaeN0qO0hy93UfyM4zA9HncWNqiu+Ec1gTKSI7KDd8=",
                            "s4":"M�7J��\u001c��G�3���y�Xڢ��\u001c�\u0004�H��\r�",
                            "b5":"AAAAF0h26AA=",
                            "s5":"\u0000\u0000\u0000\u0017Hv�\u0000",
                            "b6":"AAAANGMLifw=",
                            "s6":"\u0000\u0000\u00004c\u000b��",
                            "str":"OP_RETURN 534c5000 01 53454e44 4de69e374a8ed21cbddd47f2338cc0f479dc58daa2bbe11cd604ca488eca0ddf 000000174876e800 00000034630b89fc",
                            "e":{
                                "v":0,
                                "i":0
                            },
                            "h1":"534c5000",
                            "h2":"01",
                            "h3":"53454e44",
                            "h4":"4de69e374a8ed21cbddd47f2338cc0f479dc58daa2bbe11cd604ca488eca0ddf",
                            "h5":"000000174876e800",
                            "h6":"00000034630b89fc"
                        },
                        {
                            "i":1,
                            "b0":{
                                "op":118
                            },
                            "b1":{"op":169},
                            "b2":"dgFWHSEhP62WFiQygwWJwSUQoSc=",
                            "s2":"v\u0001V\u001d!!?��\u0016$2�\u0005��%\u0010�'",
                            "b3":{"op":136},
                            "b4":{"op":172},
                            "str":"OP_DUP OP_HASH160 7601561d21213fad96162432830589c12510a127 OP_EQUALVERIFY OP_CHECKSIG",
                            "e":{"v":546,"i":1,"a":"qpmqz4sayysnltvkzcjr9qc938qj2y9pyu9hvr7dxg"},
                            "h2":"7601561d21213fad96162432830589c12510a127"
                        },
                        {
                            "i":2,
                            "b0":{"op":118},
                            "b1":{"op":169},
                            "b2":"dgFWHSEhP62WFiQygwWJwSUQoSc=",
                            "s2":"v\u0001V\u001d!!?��\u0016$2�\u0005��%\u0010�'",
                            "b3":{"op":136},
                            "b4":{"op":172},
                            "str":"OP_DUP OP_HASH160 7601561d21213fad96162432830589c12510a127 OP_EQUALVERIFY OP_CHECKSIG",
                            "e":{
                                "v":546,
                                "i":2,
                                "a":"qpmqz4sayysnltvkzcjr9qc938qj2y9pyu9hvr7dxg"
                            },
                            "h2":"7601561d21213fad96162432830589c12510a127"
                        },
                        {
                            "i":3,
                            "b0":{"op":118},
                            "b1":{"op":169},
                            "b2":"dgFWHSEhP62WFiQygwWJwSUQoSc=",
                            "s2":"v\u0001V\u001d!!?��\u0016$2�\u0005��%\u0010�'",
                            "b3":{"op":136},
                            "b4":{"op":172},
                            "str":"OP_DUP OP_HASH160 7601561d21213fad96162432830589c12510a127 OP_EQUALVERIFY OP_CHECKSIG",
                            "e":{
                                "v":55701,
                                "i":3,
                                "a":"qpmqz4sayysnltvkzcjr9qc938qj2y9pyu9hvr7dxg"
                            },
                            "h2":"7601561d21213fad96162432830589c12510a127"
                        }
                    ],
                    "blk":{
                        "i":648836,
                        "h":"00000000000000000130f02272ea3b821036e0842527885fd2800de8351c869a",
                        "t":1597719690
                    }
                },
                {
                    "_id":"5f3b44e505aea95114959e01",
                    "tx":{"h":"fee3de4161cb413c4a046b94b64b93154c6ef91100d04f8bf0b9287259e963ff"},
                    "in":[{
                        "i":0,
                        "b0":"MEQCIEMxfYP09r+CGcgDQ9OpjTt2SSz8QXSSdcpDxJpkNWeiAiB3xXSqh1iWFK1OqQjO9+NGrS/eF4ps0dDnIDILEYtXzEE=",
                        "b1":"At0D5ajaTpnSC3tnCIGFmUvxHrUZePaWmU67qCQXSick",
                        "str":"3044022043317d83f4f6bf8219c80343d3a98d3b76492cfc41749275ca43c49a643567a2022077c574aa87589614ad4ea908cef7e346ad2fde178a6cd1d0e720320b118b57cc41 02dd03e5a8da4e99d20b7b67088185994bf11eb51978f696994ebba824174a2724",
                        "e":{
                            "h":"f00d6510ef473d2614e142d598979a1af5848190dc3d276837528b09b836489c",
                            "i":1,
                            "a":"qq5hgg4e0uavrlgwqtsu7092jpkef560yyedt26jks"
                        },
                        "h0":"3044022043317d83f4f6bf8219c80343d3a98d3b76492cfc41749275ca43c49a643567a2022077c574aa87589614ad4ea908cef7e346ad2fde178a6cd1d0e720320b118b57cc41",
                        "h1":"02dd03e5a8da4e99d20b7b67088185994bf11eb51978f696994ebba824174a2724"
                    }],
                    "out":[
                        {
                            "i":0,
                            "b0":{"op":118},
                            "b1":{"op":169},
                            "b2":"o8AusmfBJRB9yfT3+pbFnk+0vzA=",
                            "s2":"��.�g�%\u0010}�����ŞO��0",
                            "b3":{"op":136},
                            "b4":{"op":172},
                            "str":"OP_DUP OP_HASH160 a3c02eb267c125107dc9f4f7fa96c59e4fb4bf30 OP_EQUALVERIFY OP_CHECKSIG",
                            "e":{
                                "v":9850,
                                "i":0,
                                "a":"qz3uqt4jvlqj2yrae860075kck0yld9lxq93gt743g"
                            },
                            "h2":"a3c02eb267c125107dc9f4f7fa96c59e4fb4bf30"
                        },
                        {
                            "i":1,
                            "b0":{"op":118},
                            "b1":{"op":169},
                            "b2":"KXQiuX86wf0OAuHPPKqQbZTTTyE=",
                            "s2":")t\"�:��\u000e\u0002��<��m��O!",
                            "b3":{"op":136},
                            "b4":{"op":172},
                            "str":"OP_DUP OP_HASH160 297422b97f3ac1fd0e02e1cf3caa906d94d34f21 OP_EQUALVERIFY OP_CHECKSIG",
                            "e":{
                                "v":14832463,
                                "i":1,
                                "a":"qq5hgg4e0uavrlgwqtsu7092jpkef560yyedt26jks"
                            },
                            "h2":"297422b97f3ac1fd0e02e1cf3caa906d94d34f21"
                        }
                    ],
                    "blk":{
                        "i":648836,
                        "h":"00000000000000000130f02272ea3b821036e0842527885fd2800de8351c869a",
                        "t":1597719690
                    }
                }
            ]
        }
        self.expectation_1 = json.dumps(data_1)
        self.output = "('bch', 'bitcoincash:qr3ndk3syx9kvkna3rgk48vf5n8dft2ruylpkn54rq', 'de0847e87c1387b72d02f5942569f3ff5b1ef3c7eafd623fc4d073f9d4436e9c', 715.01830329, 'bitdbquery', None, 0)\n('bch', 'bitcoincash:qplump0lqjv89xnpwpstg6jhhkjw2a9jqyawg7j0v5', 'de0847e87c1387b72d02f5942569f3ff5b1ef3c7eafd623fc4d073f9d4436e9c', 14.62212686, 'bitdbquery', None, 1)\n('bch', 'bitcoincash:qp9sl7qt3pg2h4vs5z2w28hw865u672ajqtfevzrqr', '2d2e956f4c32809cf5571f92b38a21a787e0f8bd03ad4f4731b0e0d6fb5a35b7', 2816.49670716, 'bitdbquery', None, 0)\n('bch', 'bitcoincash:qr37q87cuvwtcvvgyv0j8dvvh0akpkd9uyxc8vg70y', '2d2e956f4c32809cf5571f92b38a21a787e0f8bd03ad4f4731b0e0d6fb5a35b7', 8.14, 'bitdbquery', None, 1)\n('bch', 'bitcoincash:qqf3ql5mpajyjrm9vx4x6q7mvsxk2zqayvqj3ntjua', '2d2e956f4c32809cf5571f92b38a21a787e0f8bd03ad4f4731b0e0d6fb5a35b7', 0.2096, 'bitdbquery', None, 2)\n"
    
    def test(self):
        self.requests_mock.get(self.url_1, text=self.expectation_1)
        tasks.bitdbquery() 
        captured = self.capsys.readouterr()
        assert captured.out == self.output
        