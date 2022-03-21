from web3.datastructures import AttributeDict
from hexbytes import HexBytes
# NOTE: return values might be incomplete from the actual, they might only include the fields that the code needs

test_block_response = AttributeDict({
    "__mock": True,
    "extraData": HexBytes("0x"),
    "gasLimit": 1000000000,
    "gasUsed": 79041,
    "hash": HexBytes("0x70d6332dbbe96b62bfde145dcff69f2c76c2da598a9cefff07601a2b93510dd2"),
    "logsBloom": HexBytes("0x00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"),
    "miner": "0x930C23CE7536B0ede6AfE7754134d4011217D6AA",
    "mixHash": HexBytes("0x0000000000000000000000000000000000000000000000000000000000000000"),
    "nonce": HexBytes("0x0000000000000000"),
    "number": 3586044,
    "parentHash": HexBytes("0x766c33debd89e31dca0ae16cf5fa17d2720a587b1a94a1cdd59c5c6659e03019"),
    "receiptsRoot": HexBytes("0x0000000000000000000000000000000000000000000000000000000000000000"),
    "sha3Uncles": HexBytes("0x0000000000000000000000000000000000000000000000000000000000000000"),
    "size": 735,
    "stateRoot": HexBytes("0x0d2d381a9de31b91c15e08bdec8ddc94ff8131e2916bca9e93adc726b19714ef"),
    "timestamp": 1647567385,
    "totalDifficulty": 0,
    "transactions": [
        AttributeDict({
            "blockHash": HexBytes("0x70d6332dbbe96b62bfde145dcff69f2c76c2da598a9cefff07601a2b93510dd2"),
            "blockNumber": 3586044,
            "from": "0xfea305D5Fe76cf6Ea4A887234264a256AD269792",
            "gas": 84061,
            "gasPrice": 1046739556,
            "hash": HexBytes("0xe40c6856318c5ae33e4c1e61d54a6047e3c917d7bd64ccdd63f5a5f4b389c7e6"),
            "input": "0x84f51869000000000000000000000000000000000000000000000000000000000000753000000000000000000000000000000000000000000000000000000000000000c8",
            "nonce": 22674,
            "to": "0x659F04F36e90143fCaC202D4BC36C699C078fC98",
            "transactionIndex": 0,
            "value": 0,
            "v": 67,
            "r": HexBytes("0x196561a8f84f68eb5ef9a7190d842d9d5e413b568cfd30269f01f45dffd1d6e4"),
            "s": HexBytes("0x0de51eff42dded690ba3c00a7b136bdbe26ddc7d275ffe93fa47c56b2220ccb8")
        })
    ],
    "transactionsRoot": HexBytes("0x0000000000000000000000000000000000000000000000000000000000000000"),
    "uncles": [],
})

test_block_logs = [
    AttributeDict({'address': '0x265bD28d79400D55a1665707Fa14A72978FA6043',
        'topics': [
            HexBytes('0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'),
            HexBytes('0x000000000000000000000000fea305d5fe76cf6ea4a887234264a256ad269792'),
            HexBytes('0x000000000000000000000000659f04f36e90143fcac202d4bc36c699c078fc98')
        ],
        'data': '0x0000000000000000000000000000000000000000000000000000000000007530',
        'blockNumber': 3586044,
        'transactionHash': HexBytes('0xe40c6856318c5ae33e4c1e61d54a6047e3c917d7bd64ccdd63f5a5f4b389c7e6'),
        'transactionIndex': 0,
        'blockHash': HexBytes('0x70d6332dbbe96b62bfde145dcff69f2c76c2da598a9cefff07601a2b93510dd2'),
        'logIndex': 0,
        'removed': False
    }),
    AttributeDict({
        'address': '0x659F04F36e90143fCaC202D4BC36C699C078fC98',
        'topics': [
            HexBytes('0xe3d4187f6ca4248660cc0ac8b8056515bac4a8132be2eca31d6d0cc170722a7e'),
            HexBytes('0x000000000000000000000000fea305d5fe76cf6ea4a887234264a256ad269792')
        ],
        'data': '0x0000000000000000000000000000000000007530000000c8000000006233e219',
        'blockNumber': 3586044,
        'transactionHash': HexBytes('0xe40c6856318c5ae33e4c1e61d54a6047e3c917d7bd64ccdd63f5a5f4b389c7e6'),
        'transactionIndex': 0,
        'blockHash': HexBytes('0x70d6332dbbe96b62bfde145dcff69f2c76c2da598a9cefff07601a2b93510dd2'),
        'logIndex': 1,
        'removed': False
    })
]

test_tx = AttributeDict({
    "__mock": True,
    "blockNumber": 3572704, 
    "hash": HexBytes("0xf5436214228b01a06f328efeb8ac841d10e3b5ab747014dcfeab97a63f5cc827"),
    "to": "0x3207d65b4D45CF617253467625AF6C1b687F720b",
    "from": "0x8De86AD10f3F9EE5dEC5773D04326896553A0D2A",
    "value": 350000000000000000,
    "input": "0x314262487a783956634d6f7069436562644c65446639546f5470766679515070586d",
    "gas": 26582,
    "gasPrice": 1046739556,
})

test_sep20_transfer_tx = AttributeDict({
    "__mock": True,
    "blockNumber": 3570384, 
    "hash": HexBytes("0x22fbe3c0b651e09a445f2b3a70f02de7539e98f5f6b73d636a3659c7051777d2"),
    "to": "0x5fA664f69c2A4A3ec94FaC3cBf7049BD9CA73129",
    "from": "0x827697b2888612a48d572A40B66cD4C552E52260",
    "value": 0,
    "input": "0xa9059cbb0000000000000000000000005bdc97ef6db3f69ba6e4d73550aa57e54a9667130000000000000000000000000000000000000000000000035c6c3f828a380000",
    "gas": 49095,
    "gasPrice": 1046739556,
})

test_sep20_transfer_tx_receipt = AttributeDict({
    "__mock": True,
    "status": 1,
    "logs": [
        AttributeDict({
            "address": "0x5fA664f69c2A4A3ec94FaC3cBf7049BD9CA73129",
            "topics": [
                HexBytes("0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"),
                HexBytes("0x000000000000000000000000827697b2888612a48d572a40b66cd4c552e52260"),
                HexBytes("0x0000000000000000000000005bdc97ef6db3f69ba6e4d73550aa57e54a966713"),
            ],
            "data": "0x0000000000000000000000000000000000000000000000035c6c3f828a380000",
            "blockNumber": 3570384,
            "transactionHash": HexBytes("0x22fbe3c0b651e09a445f2b3a70f02de7539e98f5f6b73d636a3659c7051777d2"),
            "transactionIndex": 0,
            "blockHash": HexBytes("0x0e4381d4a38d5606a4656f5751fa377f392e5e8ebb6fa5c8a7f42089f5f5bf68"),
            "logIndex": 0,
            "removed": False,
        })
    ]
})

test_sbch_query_tx_by_addr = [
    AttributeDict({
        'blockHash': '0x6a6509625946f46727be6df14f9e1731666260fe4931040114266e9aa4cf4ae6',
        'blockNumber': '0x8af41',
        'from': '0xd56e9af0243ffbbe4c6a801ad8f20a097d247122',
        'gas': '0x65b6',
        'gasPrice': '0x3e95ba80',
        'hash': '0x106afbfde9e02f8cd21d8b29568a43a753460d019b4a672822c129281524369f',
        'input': '0x',
        'nonce': '0x78c',
        'to': '0xda34ad1848424cca7e0ff55c7ef6c6fe46833456',
        'transactionIndex': '0x0',
        'value': '0x1c6bf52634000',
        'v': '0x43',
        'r': '0xe6ea923b481d48c5c181c6311b38a115bd73cd300cb167e15c34f5d0cca1fc6d',
        's': '0x14221e625532f8d705eea31654f0076a92744d679181497babd86000ff96885'
    }),
    AttributeDict({
        'blockHash': '0xedb9b2d154b526eb14411ab9becd44b4ef1cd61ce7aea0bb949b5d9a1bfe9e71',
        'blockNumber': '0x8afe7',
        'from': '0xd56e9af0243ffbbe4c6a801ad8f20a097d247122',
        'gas': '0x65b6',
        'gasPrice': '0x3e95ba80',
        'hash': '0x2d0ec70c0d964abe8faedef73e99c632ab3b40d1ceea4165496234311b33cde2',
        'input': '0x',
        'nonce': '0x79a',
        'to': '0xda34ad1848424cca7e0ff55c7ef6c6fe46833456',
        'transactionIndex': '0x1',
        'value': '0x1c6bf52634000',
        'v': '0x43',
        'r': '0x9ef81881f233add23142010398660d5c777b88d5a57d3a1af14c6c6da3bf9fbb',
        's': '0x2b4f3e9e89b6ae17d639c923520263da93c24f4bc8b137d11aff66cf86673415'
    }),
    AttributeDict({
        'blockHash': '0x406e80d0caeebb8b5ce72dad557f2d4ca3b8a01f09a947518b50f5433692defc',
        'blockNumber': '0x101c3d',
        'from': '0xda34ad1848424cca7e0ff55c7ef6c6fe46833456',
        'gas': '0x21a87',
        'gasPrice': '0x3e95ba80',
        'hash': '0x6a40e73b609ee1c3883e42281fd450d6ce718fa2bef349a0dad6fe899de97b06',
        'input': '0xe2bbb15800000000000000000000000000000000000000000000000000000000000000050000000000000000000000000000000000000000000000000000000000000000',
        'nonce': '0x4',
        'to': '0x3a7b9d0ed49a90712da4e087b17ee4ac1375a5d4',
        'transactionIndex': '0x0',
        'value': '0x0',
        'v': '0x44',
        'r': '0x3e5d4fe853c0358024a629e90e5663c68c3a9ae881f14a070e5d1d13a6c82d94',
        's': '0x5101d2f135090fc4c4e477bbce7f3c8e99630d598cc901fd4cf9a253e9a6a16a'}),
    AttributeDict({
        'blockHash': '0x03df87c5120439af79ef2202e9f4e7de262c0a698204862dd7578d60abb985c7',
        'blockNumber': '0x101c48',
        'from': '0xda34ad1848424cca7e0ff55c7ef6c6fe46833456',
        'gas': '0xe7bd',
        'gasPrice': '0x3e95ba80',
        'hash': '0x9b3ad1d37abe8a6a612739b16ab1efd8e23bd4bdf119a5209fe7074dee1ca9bf',
        'input': '0x095ea7b3000000000000000000000000c41c680c60309d4646379ed62020c534eb67b6f4ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff',
        'nonce': '0x5',
        'to': '0x5fa664f69c2a4a3ec94fac3cbf7049bd9ca73129',
        'transactionIndex': '0x1',
        'value': '0x0',
        'v': '0x44',
        'r': '0xb5ea501e1de627c84fde0373bec2c3367ff77ae2f84f3b647871cecfb371f2f0',
        's': '0x53b50ed4c12e90b79f640341ac9c81437d36190e58bc9a4351524d9c2419fdf0'
    })

]


test_sbch_query_transfer_events = [
    AttributeDict({
        'address': '0x7b2B3C5308ab5b2a1d9a94d20D35CCDf61e05b72',
        'topics': [
            HexBytes('0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'),
            HexBytes('0x000000000000000000000000c396c8a9b0d23b9475f6cd60d93efc62d920bc5b'),
            HexBytes('0x000000000000000000000000e057cfdce29b7f7606e84b14cd0cdd0ed5114fc1')
        ],
        'data': '0x0000000000000000000000000000000000000000000000000de0b6b3a763ffff',
        'blockNumber': 3632532,
        'transactionHash': HexBytes('0xb6ceeacf89f0491e6dfe112c12990187f75b466a0752be4020aa3e464f1272c0'),
        'transactionIndex': 0,
        'blockHash': HexBytes('0x02ea77b7161432635403dd0204f3906096465723378a569425bec49a79deaee3'),
        'logIndex': 0,
        'removed': False
    }),
    AttributeDict({'address': '0xc4eb62f900ae917f8F86366B4C1727eb526D1275',
        'topics': [
            HexBytes('0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'),
            HexBytes('0x000000000000000000000000b457805fedfc2467877dcfa153636c1d22ae6c6f'),
            HexBytes('0x000000000000000000000000e057cfdce29b7f7606e84b14cd0cdd0ed5114fc1')
        ],
        'data': '0x00000000000000000000000000000000000000000000000000038d7ea4c67fff',
        'blockNumber': 3632532,
        'transactionHash': HexBytes('0xb6ceeacf89f0491e6dfe112c12990187f75b466a0752be4020aa3e464f1272c0'),
        'transactionIndex': 0,
        'blockHash': HexBytes('0x02ea77b7161432635403dd0204f3906096465723378a569425bec49a79deaee3'),
        'logIndex': 3,
        'removed': False
    }),
    AttributeDict({
        'address': '0x24d8d5Cbc14FA6A740c3375733f0287188F8dF3b',
        'topics': [
            HexBytes('0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'),
            HexBytes('0x000000000000000000000000e4d74af73114f72bd0172fc7904852ee2e2b47b0'),
            HexBytes('0x000000000000000000000000cb771962b319d821ab083e1e14800eef9a9f7b44')
        ],
        'data': '0x0000000000000000000000000000000000000000000000347cd822e6e296cdd5',
        'blockNumber': 3633028,
        'transactionHash': HexBytes('0x1d8add6f0ea5ae2c6101941b1a0cd7eaa66c21c5728e7fb0e887c185040b4ed8'),
        'transactionIndex': 1,
        'blockHash': HexBytes('0x7283109e3e9e3307f005df5c34443c03734513cfa78af8ff14b06908efeb6025'),
        'logIndex': 6,
        'removed': False
    }),
    AttributeDict({
        'address': '0x265bD28d79400D55a1665707Fa14A72978FA6043',
        'topics': [
            HexBytes('0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'),
            HexBytes('0x000000000000000000000000659f04f36e90143fcac202d4bc36c699c078fc98'),
            HexBytes('0x00000000000000000000000049029059a78a63e3069a816e559453d7f856c241')
        ],
        'data': '0x00000000000000000000000000000000000000000000000000000000000217f0',
        'blockNumber': 3633029,
        'transactionHash': HexBytes('0xba86dc6810db51f214b3868603754251897db666b232d02cd4f03da8b96c3be0'),
        'transactionIndex': 1,
        'blockHash': HexBytes('0x889fdec4d1b21da7b5957323f6ead9944e27cf081eeeac0bb3bbc308be3e46ec'),
        'logIndex': 0,
        'removed': False
    })
]