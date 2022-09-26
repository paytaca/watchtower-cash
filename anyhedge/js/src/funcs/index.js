import { compileContract, create } from './create.js'
import { calculateFundingAmounts, completeFundingProposal } from './funding.js'
import { fundHedgePosition } from './liquidity-provider.js'
import { completeMutualRedemption } from './mutual-settlement.js'
import { parseOracleMessage, getPriceMessages } from './price.js'
import { parseSettlementTransactions, settleContractMaturity, liquidateContract } from './settlement.js'
import { getContractStatus } from './status.js'
import { sum, asyncSum } from './test.js'

const funcs = {
    compileContract,
    create,
    calculateFundingAmounts,
    completeFundingProposal,
    fundHedgePosition,
    completeMutualRedemption,
    parseOracleMessage,
    getPriceMessages,
    parseSettlementTransactions,
    settleContractMaturity,
    liquidateContract,
    getContractStatus,
    sum,
    asyncSum,
}

export default funcs
