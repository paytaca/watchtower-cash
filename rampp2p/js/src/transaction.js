import BCHJS from '@psf/bch-js';
const bchjs = new BCHJS({
    restURL: 'https://bchn.fullstack.cash/v5/',
    apiToken: process.env.BCHJS_TOKEN
});

run();

async function run() {
    const txid = process.argv[2]
    let txn = null
    try {
        const raw_txn = await bchjs.Electrumx.txData(txid)
        txn = await parse_raw_transaction(raw_txn, txid)
        console.log(JSON.stringify(txn))
    } catch (error) {
        console.log(JSON.stringify({'error': error.toString()}))
    }
}

async function parse_raw_transaction(txn, txid) {
    let timestamp = null
    let confirmations = null
    if (txn.details.hasOwnProperty('time')) timestamp = txn.details.time
    if (txn.details.hasOwnProperty('confirmations')) confirmations = txn.details.confirmations
    const vin = txn.details.vin
    const vout = txn.details.vout

    // inputs
    let inputs = []
    for (let i = 0; i < vin.length; i++) {
        let prevOut = vin[i]
        let prevOutTx = await bchjs.Electrumx.txData(prevOut.txid)
        let address = prevOutTx.details.vout[prevOut.vout].scriptPubKey.addresses[0]
        let value = prevOutTx.details.vout[prevOut.vout].value
        inputs.push({
            "address": address,
            "value": value
        })
    }

    // outputs
    const outputs = []
    for (let i = 0; i < vout.length;  i++) {
        let address = vout[i].scriptPubKey.addresses[0]
        let value = vout[i].value
        outputs.push({
            "address": address,
            "value": value
        })
    }

    const results = {
        "txid": txid,
        "timestamp": timestamp,
        "confirmations": confirmations,
        "inputs": inputs,
        "outputs": outputs
    }

    return results
}