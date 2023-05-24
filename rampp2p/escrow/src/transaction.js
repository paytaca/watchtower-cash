const BCHJS = require('@psf/bch-js');
const bchjs = new BCHJS({
    restURL: 'https://bchn.fullstack.cash/v5/',
    apiToken: process.env.BCHJS_TOKEN
})

run();

async function run() {
    try {
        const txid = process.argv[2]
        const result = await bchjs.Electrumx.txData(txid)
        const vin = result.details.vin
        const vout = result.details.vout

        // inputs
        let inputs = []
        for (let i = 0; i < vin.length; i++) {
            let prevOut = vin[i]
            let prevOutTx = await bchjs.Electrumx.txData(prevOut.txid)
            let address = prevOutTx.details.vout[prevOut.vout].scriptPubKey.addresses[0]
            let value = prevOutTx.details.vout[prevOut.vout].value
            inputs.push({
                "address": address,
                "amount": value
            })
        }

        // outputs
        let outputs = []
        for (let i = 0; i < vout.length; i++) {
            let address = vout[i].scriptPubKey.addresses[0]
            let value = vout[i].value
            outputs.push({
                "address": address,
                "amount": value
            })
        }
        const response = {
            "inputs": inputs,
            "outputs": outputs
        }
        console.log(JSON.stringify(response))
    } catch (error) {
        console.log(JSON.stringify(error))
    }
}