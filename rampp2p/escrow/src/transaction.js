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
        const vout = result.details.vout
        const outputs = []
        for (let i = 0; i < vout.length; i++) {
            let address = vout[i].scriptPubKey.addresses[0]
            let value = vout[i].value
            outputs.push({
                "address": address,
                "amount": value
            })
        }
        const response = {
            "outputs": outputs
        }
        console.log(JSON.stringify(response))
    } catch (error) {
        console.log(JSON.stringify(error))
    }
}