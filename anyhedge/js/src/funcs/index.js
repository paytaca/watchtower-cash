import { compileContract, create } from './create.js'
import { matchHedgePositionOffer, fundHedgePosition, matchAndFundHedgePositionOffer } from './liquidity-provider.js'
import { parseOracleMessage, getPriceMessages } from './price.js'
import { getContractStatus } from './status.js'
import { sum, asyncSum } from './test.js'

const funcs = {
    compileContract,
    create,
    matchHedgePositionOffer,
    fundHedgePosition,
    matchAndFundHedgePositionOffer,
    parseOracleMessage,
    getPriceMessages,
    getContractStatus,
    sum,
    asyncSum,
}

export default funcs
