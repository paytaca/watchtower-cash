const { ElectrumNetworkProvider, Contract, SignatureTemplate } = require('cashscript');
const { compileFile } = require('cashc');
const path = require('path');
const BCHJS = require('@psf/bch-js');

// params
const ACTION = process.argv[2]; // 'contract' | 'seller-release' | 'arbiter-release' | 'refund'

const ARBITR_PUBKEY = process.argv[3]
const SELLER_PUBKEY = process.argv[4]
const BUYER_PUBKEY = process.argv[5]

const SERVCR_PUBKEY = process.env.SERVICER_PK
const SERVCR_ADDR = process.env.SERVICER_ADDR
const TRADING_FEE = parseInt(process.env.TRADING_FEE)
const ARBITRATION_FEE = parseInt(process.env.ARBITRATION_FEE)
const HARDCODED_FEE = 1000;

const bchjs = new BCHJS({
    restURL: 'https://bchn.fullstack.cash/v5/',
    apiToken: process.env.BCHJS_TOKEN
  });
  
const NETWORK = 'mainnet';

run();

async function run() {

    // Compile the escrow contract to an artifact object
    const artifact = compileFile(path.join(__dirname, 'escrow.cash'));

    // Initialise a network provider for network operations on TESTNET3
    const provider = new ElectrumNetworkProvider(NETWORK);

    const [arbiterPkh, buyerPkh, sellerPkh, servicerPkh] = getPubKeyHash();
    
    // Instantiate a new contract providing the constructor parameters
    // { arbiter: arbiterPkh, buyer: buyerPkh, seller, sellerPkh, 
    // servicer: servicerPkh, tradingFee: tradingFee, arbitrationFee: arbitrationFee }
    const contractParams = [arbiterPkh, buyerPkh, sellerPkh, servicerPkh, TRADING_FEE, ARBITRATION_FEE];
    const contract = new Contract(artifact, contractParams, provider);

    if (ACTION == 'contract') {
        process.stdout.write(contract.address)
        return
    }

    if (ACTION == 'balance') {
        return await getContractBalance(contract)
    }

    const callerSig = process.argv[6]
    const recipientAddr = process.argv[7]
    const arbiterAddr = process.argv[8]
    const amount = process.argv[9]

    if (ACTION == 'seller-release') {
        await release(contract, SELLER_PUBKEY, callerSig, recipientAddr, SERVCR_ADDR, arbiterAddr, amount)
    }

    if (ACTION == 'arbiter-release') {
        await release(contract, ARBITR_PUBKEY, callerSig, recipientAddr, SERVCR_ADDR, arbiterAddr, amount)
    }

    if (ACTION == 'refund') {
        await refund(contract, SELLER_PUBKEY, callerSig, recipientAddr, SERVCR_ADDR, arbiterAddr, amount);
    }
}

function getPubKeyHash() {  
    // produce the public key hashes
    const arbiterPkh = bchjs.Crypto.hash160(Buffer.from(ARBITR_PUBKEY, "hex"));
    const buyerPkh = bchjs.Crypto.hash160(Buffer.from(BUYER_PUBKEY, "hex"));
    const sellerPkh = bchjs.Crypto.hash160(Buffer.from(SELLER_PUBKEY, "hex"));
    const servicerPkh = bchjs.Crypto.hash160(Buffer.from(SERVCR_PUBKEY, "hex"));
    return [arbiterPkh, buyerPkh, sellerPkh, servicerPkh];
}

async function getContractBalance(contract) {
    const balance = await contract.getBalance();
    return bchjs.BitcoinCash.toBitcoinCash(Number(balance))
}

/**
 * Release the funds to the buyer. 
 * The contract should fail if the caller is not seller or the arbiter.
 * The contract should fail if the amount sent is incorrect.
 * The contract should fail if the output[0] is not the buyer.
 * The contract should fail if the output[1] is not the servicer.
 * The contract should fail if the output[2] is not the arbiter.
 * @param {Contract} contract - The instance of escrow contract.
 * @param {string} callerPk - The public key of transaction sender (arbiter/seller).
 * @param {string} callerSig - The signature of transaction sender (arbiter/seller).
 * @param {string} recipient - The cash address of the recipient (buyer).
 * @param {string} servicer - The cash address of the servicer.
 * @param {string} arbiter - The cash address of the arbiter.
 * @param {number} amount - The transaction amount in BCH.
 */
async function release(contract, callerPk, callerSig, recipient, servicer, arbiter, amount) {
    let result = {}
    let txInfo;

    try {
        // convert amount from BCH to satoshi
        const sats = Math.floor(bchjs.BitcoinCash.toSatoshi(Number(amount)));

        /** 
         * output[0]: {to: `buyer address`, amount: `trade amount`}
         * output[1]: {to: `servicer address`, amount: `trade fee`}
         * output[2]: {to: `arbiter address`, amount: `arbitration fee`}
         * */ 
        const outputs = [
            {to: recipient, amount: sats},
            {to: servicer, amount: TRADING_FEE},
            {to: arbiter, amount: ARBITRATION_FEE}
        ]

        txInfo = await contract.functions
            .release(callerPk, callerSig)
            .to(outputs)
            .withHardcodedFee(HARDCODED_FEE)
            .send();
        
        result = {
            success: true,
            txInfo
        };

    } catch(err) {
        result = {
            success: false,
            reason: String(err),
            txInfo
        };
    }  
    console.log('result:', JSON.stringify(result));
}

/**
 * Refund the funds back to the seller.
 * The contract should fail if caller is not the arbiter.
 * The contract should fail if the amount sent is incorrect.
 * The contract should fail if the output[0] is not the seller.
 * The contract should fail if the output[1] is not the servicer.
 * The contract should fail if the output[2] is not the arbiter.
 * @param {Contract} contract - The instance of escrow contract.
 * @param {string} arbiterPk - The public key of arbiter.
 * @param {string} arbiterSig - The signature of arbiter.
 * @param {string} recipient - The cash address of the recipient (seller).
 * @param {string} servicer - The cash address of the servicer.
 * @param {string} arbiter - The cash address of the arbiter.
 * @param {number} amount - The transaction amount in BCH
 */
async function refund(contract, arbiterPk, arbiterSig, recipient, servicer, arbiter, amount) {
    let result = {}
    let txInfo;

    try {
        // convert amount from BCH to satoshi
        const sats = Math.floor(bchjs.BitcoinCash.toSatoshi(Number(amount)));

        console.log("sending to:")
        console.log(`${sats} to recipient: ${recipient}`)
        console.log(`${TRADING_FEE} to servicer: ${wallet.servicer.address}`)
        console.log(`${ARBITRATION_FEE} to arbiter: ${wallet.arbiter.address}`)

        /** 
         * output[0]: {to: `seller address`, amount: `trade amount`}
         * output[1]: {to: `servicer address`, amount: `trade fee`}
         * output[2]: {to: `arbiter address`, amount: `arbitration fee`}
         * */ 
        const outputs = [
            {to: recipient, amount: sats},
            {to: servicer, amount: TRADING_FEE},
            {to: arbiter, amount: ARBITRATION_FEE}
        ]
        
        txInfo = await contract.functions
            .refund(arbiterPk, arbiterSig)
            .to(outputs)
            .withHardcodedFee(HARDCODED_FEE)
            .send();

        result = {
            success: true,
            txInfo
        };

    } catch(err) {
        result = {
            success: false,
            reason: String(err),
            txInfo
        };
    }
    console.log('result:', JSON.stringify(result));
}