const BCHJS = require('@psf/bch-js');
// const fetch = require('node-fetch');
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
    } catch (error) {
        // console.log(JSON.stringify({'error': error}))
        // console.log(`Failed to fetch txn via bchjs: ${JSON.stringify(error)}`)

        const url = `https://watchtower.cash/api/transactions/${txid}/`
        txn = await get_transaction(url)
        // if (txn == {} || txn.details == null) {
        //     const url = `https://chipnet.watchtower.cash/api/transactions/${txid}/`
        //     txn = await get_transaction(url)
        // }
    }
    console.log(JSON.stringify(txn))

    // try {
    //     let result = await bchjs.Electrumx.txData(txid)
    //     const vin = result.details.vin
    //     const vout = result.details.vout

    //     // get tx inputs
    //     let inputs = []
    //     for (let i = 0; i < vin.length; i++) {
    //         let prevOut = vin[i]
    //         let prevOutTx = await bchjs.Electrumx.txData(prevOut.txid)
    //         let address = prevOutTx.details.vout[prevOut.vout].scriptPubKey.addresses[0]
    //         let value = prevOutTx.details.vout[prevOut.vout].value
    //         inputs.push({
    //             "address": address,
    //             "value": value
    //         })
    //     }

    //     // get tx outputs
    //     let outputs = []
    //     for (let i = 0; i < vout.length; i++) {
    //         let address = vout[i].scriptPubKey.addresses[0]
    //         let value = vout[i].value
    //         outputs.push({
    //             "address": address,
    //             "value": value
    //         })
    //     }
    //     const response = {
    //         "txid": txid,
    //         "inputs": inputs,
    //         "outputs": outputs,
    //         "confirmations": result.details.confirmations
    //     }
    //     console.log(JSON.stringify(response))
    // } catch (error) {
    //     console.log(JSON.stringify(error))
    // }
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
        // console.log('vin[i]:', vin[i])
        let prevOut = vin[i]
        let prevOutTx = await bchjs.Electrumx.txData(prevOut.txid)
        let address = prevOutTx.details.vout[prevOut.vout].scriptPubKey.addresses[0]
        let value = prevOutTx.details.vout[prevOut.vout].value
        inputs.push({
            "address": address,
            "value": value
        })
    }
    // console.log('inputs:', inputs)

    // outputs
    const outputs = []
    for (let i = 0; i < vout.length;  i++) {
        // console.log('vout[i]:', vout[i])
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

async function get_transaction(url) {
    // console.log('Refetching txn via watchtower:', url)
    try {
        const response = await fetch(url, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
            },
        })
        const data = await response.json()
        return data
    } catch(error) {
        return { "error": error.toString() }
    }   
}