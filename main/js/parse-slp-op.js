
const OP_RET_HASH = process.argv[2]

const slpParser = require('slp-parser')
const obj = slpParser.parseSLP(OP_RET_HASH)
console.log(JSON.stringify(obj))
