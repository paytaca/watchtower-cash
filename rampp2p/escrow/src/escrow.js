const { ElectrumNetworkProvider, Contract } = require('cashscript');
const { compileFile } = require('cashc');
const path = require('path');
const BCHJS = require('@psf/bch-js');
const { ec: EC } = require('elliptic');

// params
const ACTION = process.argv[2]; // 'contract' | 'seller-release' | 'arbiter-release' | 'refund'

const ARBITR_PUBKEY = process.argv[3]
const BUYER_PUBKEY = process.argv[4]
const SELLER_PUBKEY = process.argv[5]
// const CONTRACT_HASH = process.argv[6]
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
    const contractParams = [arbiterPkh, buyerPkh, sellerPkh, servicerPkh, TRADING_FEE, ARBITRATION_FEE];
    const contract = new Contract(artifact, contractParams, provider);

    if (ACTION == 'contract') {
        data = `{"contract_address" : "${contract.address}"}`
        console.log(data)
        return 
    }

    const callerPk = process.argv[6]
    let callerSig = process.argv[7]
    callerSig = JSON.parse(process.argv[7])
    const recipientAddr = process.argv[8]
    const arbiterAddr = process.argv[9]
    const amount = process.argv[10]

    if (ACTION == 'refund') {
        await refund(contract, callerPk, callerSig, recipientAddr, arbiterAddr, amount);
        return
    }

    if (ACTION == 'arbiter-release' || ACTION == 'seller-release') {
        await release(contract, callerPk, callerSig, recipientAddr, SERVCR_ADDR, arbiterAddr, amount)
        return
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

async function getBalances(contract, arbiterAddr, recipientAddr) {
    const rawBal = await contract.getBalance();
    const contractBal = bchjs.BitcoinCash.toBitcoinCash(Number(rawBal));
    contract = `{ "address": "${contract.address}", "balance": ${contractBal}}`
    
    // const arbiterBal = await getBCHBalance(arbiterAddr);    
    // arbiter = `{ "address": "${arbiterAddr}", "balance": ${arbiterBal}}`
    
    // const recipientBal = await getBCHBalance(recipientAddr);
    // recipientInfo = `{ "address": "${recipientAddr}", "balance": ${recipientBal}}`

    // const servicerBal = await getBCHBalance(SERVCR_ADDR);
    // servicer = `{ "address": "${SERVCR_ADDR}", "balance": ${servicerBal}}`

    // console.log(`{"contract": ${contract}, "arbiter": ${arbiter}, "recipient": ${recipientInfo}, "servicer": ${servicer}}`)
    console.log(`{"contract": ${contract}}`)
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

        await contract.functions
        .release(callerPk, callerSig, CONTRACT_HASH)
        .to(outputs)
        .withHardcodedFee(HARDCODED_FEE)
        .send();
        
        result = `{"success": "True"}`

    } catch(err) {
        result = `{"success": "False", "reason": "${String(err)}"}`
    }  
    console.log(result)
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
 * @param {string} callerSig - The signature of arbiter.
 * @param {string} recipient - The cash address of the recipient (seller).
 * @param {string} servicer - The cash address of the servicer.
 * @param {string} arbiter - The cash address of the arbiter.
 * @param {number} amount - The transaction amount in BCH
 */
async function refund(contract, callerPk, callerSig, recipient, arbiter, amount) {
    let result = {}
    try {

        // convert amount from BCH to satoshi
        const sats = Math.floor(bchjs.BitcoinCash.toSatoshi(Number(amount)));

        /** 
         * output[0]: {to: `seller address`, amount: `trade amount`}
         * output[1]: {to: `servicer address`, amount: `trade fee`}
         * output[2]: {to: `arbiter address`, amount: `arbitration fee`}
         * */ 
        const outputs = [
            {to: recipient, amount: sats},
            {to: SERVCR_ADDR, amount: TRADING_FEE},
            {to: arbiter, amount: ARBITRATION_FEE}
        ]
        
        await contract.functions
        .refund(callerPk, callerSig)
        .to(outputs)
        .withHardcodedFee(HARDCODED_FEE)
        .send();

        result = `{"success": "True"}`
    } catch(err) {
        result = `{"success": "False", "reason": "${String(err)}"}`
    }
    console.log(result)
}

// Get the balance in BCH of a BCH address.
async function getBCHBalance (addr, verbose) {
    try {
        const result = await bchjs.Electrumx.balance(addr)

        if (verbose) console.log(result)

        // The total balance is the sum of the confirmed and unconfirmed balances.
        const satBalance = Number(result.balance.confirmed) + Number(result.balance.unconfirmed)

        // Convert the satoshi balance to a BCH balance
        const bchBalance = bchjs.BitcoinCash.toBitcoinCash(satBalance)

        return bchBalance
    } catch (err) {
        console.error('Error in getBCHBalance: ', err)
        console.log(`addr: ${addr}`)
    }
}

function verifySignature(publicKeyHex, derSignatureHex, message){
    const ec = new EC('secp256k1');

    // Load the public key from the hex representation
    const publicKey = ec.keyFromPublic(publicKeyHex, 'hex');
  
    // Verify the DER-encoded signature
    const isVerified = publicKey.verify(message, derSignatureHex, 'hex');
    console.log('isVerified: ', isVerified)
}