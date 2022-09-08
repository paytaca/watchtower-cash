import { compileContract, create } from './create.js'
import { matchHedgePositionOffer, matchAndFundHedgePositionOffer } from './liquidity-provider.js'
import { getPriceData } from './price.js'
import { sum, asyncSum } from './test.js'

const funcs = {
    compileContract,
    create,
    matchHedgePositionOffer,
    matchAndFundHedgePositionOffer,
    getPriceData,
    sum,
    asyncSum,
}

export default funcs
