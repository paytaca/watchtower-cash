import { compileContract, create } from './create.js'
import { matchHedgePositionOffer, matchAndFundHedgePositionOffer } from './liquidity-provider.js'
import { getPriceMessages, getPriceData } from './price.js'
import { sum, asyncSum } from './test.js'

const funcs = {
    compileContract,
    create,
    matchHedgePositionOffer,
    matchAndFundHedgePositionOffer,
    getPriceMessages,
    getPriceData,
    sum,
    asyncSum,
}

export default funcs
