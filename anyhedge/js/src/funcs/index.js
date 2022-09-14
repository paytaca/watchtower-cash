import { compileContract, create } from './create.js'
import { matchHedgePositionOffer, fundHedgePosition, matchAndFundHedgePositionOffer } from './liquidity-provider.js'
import { getPriceMessages } from './price.js'
import { sum, asyncSum } from './test.js'

const funcs = {
    compileContract,
    create,
    matchHedgePositionOffer,
    fundHedgePosition,
    matchAndFundHedgePositionOffer,
    getPriceMessages,
    sum,
    asyncSum,
}

export default funcs
