import { getSettlementServiceAuthToken } from './authToken.js'
import { compileContract, create } from './create.js'
import { calculateFundingAmounts, completeFundingProposal } from './funding.js'
import { completeMutualRedemption } from './mutual-settlement.js'
import { parseOracleMessage, getPriceMessages } from './price.js'
import { parseSettlementTransactions, settleContractMaturity, liquidateContract } from './settlement.js'
import { getContractStatus, getContractAccessKeys } from './status.js'
import { sum, asyncSum } from './test.js'

const funcs = {
    getSettlementServiceAuthToken,
    compileContract,
    create,
    calculateFundingAmounts,
    completeFundingProposal,
    completeMutualRedemption,
    parseOracleMessage,
    getPriceMessages,
    parseSettlementTransactions,
    settleContractMaturity,
    liquidateContract,
    getContractStatus,
    getContractAccessKeys,
    sum,
    asyncSum,
}

export default funcs
