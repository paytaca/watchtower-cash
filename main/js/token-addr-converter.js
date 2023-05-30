
const ADDRESS = process.argv[2];
const BCH_NETWORK = process.argv[3];
const CASH_TO_TOKEN_ADDR = process.argv[4];

const {
    encodeCashAddress,
    decodeCashAddress
} = require("@bitauth/libauth");

(() => {
    const prefix = BCH_NETWORK === 'mainnet' ? 'bitcoincash' : 'bchtest';
    const type = CASH_TO_TOKEN_ADDR === 'True' ? 2 : 0
    
    const decodedAddr = decodeCashAddress(ADDRESS);
    const resultAddress = encodeCashAddress(prefix, type, decodedAddr.hash);

    console.log(resultAddress);
})()
