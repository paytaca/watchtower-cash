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
