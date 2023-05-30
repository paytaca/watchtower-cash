
const BCH_ADDR = process.argv[2]

const BCHJS = require('@psf/bch-js')
const bchjs = new BCHJS()

const slpAddress = bchjs.SLP.Address.toSLPAddress(BCH_ADDR)
console.log(slpAddress)
