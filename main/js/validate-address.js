import {
    decodeCashAddress,
    CashAddressType,
} from '@bitauth/libauth';

const address = process.argv[2];
const isTokenAddress = process.argv[3];

const result = { valid: false }


try {
    const decodedAddress = decodeCashAddress(address)
    let validTypes = [
        CashAddressType.p2pkh,
        CashAddressType.p2sh,
    ]
    
    if (isTokenAddress === 'True') {
        validTypes = [
            CashAddressType.p2pkhWithTokens,
            CashAddressType.p2shWithTokens,
        ]
    }

    result.valid = validTypes.includes(decodedAddress.type)
} catch {}


console.log(JSON.stringify(result))
