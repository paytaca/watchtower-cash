import { ElectrumNetworkProvider, Contract } from 'cashscript';
import { compileFile } from 'cashc';
import BCHJS from '@psf/bch-js';
import CryptoJS from 'crypto-js';

const ARBITER_PUBKEY = Buffer.from(process.argv[2], "hex")
const BUYER_PUBKEY = Buffer.from(process.argv[3], "hex")
const SELLER_PUBKEY = Buffer.from(process.argv[4], "hex")
const TIMESTAMP = process.argv[5]
const SERVICER_PUBKEY = Buffer.from(process.env.SERVICER_PK, "hex")
const SERVICE_FEE = parseInt(process.env.SERVICE_FEE)
const ARBITRATION_FEE = parseInt(process.env.ARBITRATION_FEE)

const bchjs = new BCHJS({
    restURL: 'https://bchn.fullstack.cash/v5/',
    apiToken: process.env.BCHJS_TOKEN
  });

const NETWORK = process.env.ESCROW_NETWORK || 'mainnet';
const ADDRESS_TYPE = process.env.ADDRESS_TYPE || 'p2sh32';

(async () => {

    // Compile the escrow contract to an artifact object
    const artifact = compileFile(new URL('escrow.cash', import.meta.url));
    // Initialise a network provider for network operations
    const provider = new ElectrumNetworkProvider(NETWORK);
    const [arbiterPkh, buyerPkh, sellerPkh, servicerPkh] = getPubKeyHash();
    
    // Generate contract hash with timestamp
    const contractHash = await calculateSHA256(
        ARBITER_PUBKEY.toString("hex"),
        BUYER_PUBKEY.toString("hex"),
        SELLER_PUBKEY.toString("hex"),
        SERVICER_PUBKEY.toString("hex"),
        TIMESTAMP
    )

    // Instantiate a new contract providing the constructor parameters
    const contractParams = [
        arbiterPkh,
        buyerPkh,
        sellerPkh,
        servicerPkh,
        BigInt(SERVICE_FEE), 
        BigInt(ARBITRATION_FEE),
        contractHash];
    
    const contract = new Contract(artifact, contractParams, { provider, ADDRESS_TYPE });
    
    const data = `{"success": "true", "contract_address" : "${contract.address}"}`
    console.log(data)
})();

function getPubKeyHash() {  
    // produce the public key hashes
    const arbiterPkh = bchjs.Crypto.hash160(ARBITER_PUBKEY)
    const buyerPkh = bchjs.Crypto.hash160(BUYER_PUBKEY)
    const sellerPkh = bchjs.Crypto.hash160(SELLER_PUBKEY)
    const servicerPkh = bchjs.Crypto.hash160(SERVICER_PUBKEY)
    return [arbiterPkh, buyerPkh, sellerPkh, servicerPkh];
}

async function calculateSHA256(arbiterPk, buyerPk, sellerPk, servicerPk, timestamp) {
    const message = arbiterPk + buyerPk + sellerPk + servicerPk + timestamp
    const hash = CryptoJS.SHA256(message).toString();
    return hash
}