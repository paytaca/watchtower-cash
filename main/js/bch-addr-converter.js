
const ADDRESS = process.argv[2];
const TO_TOKEN_ADDR = process.argv[3];

import {
    decodeCashAddress,
    encodeCashAddress,
    CashAddressType,
    CashAddressNetworkPrefix,
} from '@bitauth/libauth';

(() => {
    const isTestnet = ADDRESS.split(':')[0].indexOf('test') >= 0
    const prefix = isTestnet ? CashAddressNetworkPrefix.testnet : CashAddressNetworkPrefix.mainnet
    const decodedAddr = decodeCashAddress(ADDRESS);
    let type = CashAddressType.p2pkh;

    if (TO_TOKEN_ADDR === 'True') {
        switch (decodedAddr.type) {
            case CashAddressType.p2pkh:
                type = CashAddressType.p2pkhWithTokens;
                break;
            case CashAddressType.p2sh:
                type = CashAddressType.p2shWithTokens;
                break;
            case CashAddressType.p2pkhWithTokens:
                console.log(ADDRESS)
                return
            case CashAddressType.p2shWithTokens:
                console.log(ADDRESS)
                return
        }
    } else {
        switch (decodedAddr.type) {
            case CashAddressType.p2pkh:
                console.log(ADDRESS)
                return
            case CashAddressType.p2sh:
                console.log(ADDRESS)
                return
            case CashAddressType.p2pkhWithTokens:
                type = CashAddressType.p2pkh
                break
            case CashAddressType.p2shWithTokens:
                type = CashAddressType.p2sh
                break
        }
    }

    const resultAddress = encodeCashAddress(prefix, type, decodedAddr.payload);
    console.log(resultAddress);
})()
