import { AnyHedgeManager } from '@generalprotocols/anyhedge'
import { castBigIntSafe, parseContractData } from '../utils.js'

/**
 * @typedef {Object} RedemptionData
 * @property {String} [short_key.schnorr_signature.all_outputs]
 * @property {String} [long_key.schnorr_signature.all_outputs]
 * 
 * @typedef {Object} SignedTransactionProposal
 * @property {{ satoshis:Number, txid:String, vout:Number }} input
 * @property {{ amount:Number, to:String }} output
 * @property {RedemptionData[]} redemptionDataList
 * 
 * @typedef {Object} MutualRedemptionData
 * @property {'refund' | 'early_maturation' | 'arbitrary'} redemptionType
 * @property {Number} shortSatoshis
 * @property {Number} longSatoshis
 * @property {String} shortSchnorrSig
 * @property {String} longSchnorrSig
 * @property {Number} [settlementPrice]
 */

/**
 * @param {ContractData} contractData 
 * @param {MutualRedemptionData} mutualRedemptionData
 */
export async function validateMutualRefund(contractData, mutualRedemptionData) {
  const response = { valid: false, error: undefined }

  if (contractData?.metadata?.shortInputInSatoshis !== mutualRedemptionData.shortSatoshis) {
    response.valid = false
    response.error = `short payout satoshis must be ${contractData?.metadata?.shortInputInSatoshis}`
    return response
  }

  if (contractData?.metadata?.longInputInSatoshis !== mutualRedemptionData.longSatoshis) {
    response.valid = false
    response.error = `long payout satoshis must be ${contractData?.metadata?.longInputInSatoshis}`
    return response
  }

  response.valid = true
  return response
}


/**
 * @param {ContractData} contractData 
 * @param {MutualRedemptionData} mutualRedemptionData
 */
export async function validateEarlyMaturation(contractData, mutualRedemptionData) {
  const response = { valid: false, error: undefined }

  const { settlementPrice } = mutualRedemptionData

  if (!settlementPrice || settlementPrice <= 0) {
    response.valid = false
    response.error = 'invalid settlement price'
    return response
  }

  if (settlementPrice < contractData?.parameters.lowLiquidationPrice || settlementPrice > contractData?.parameters.highLiquidationPrice) {
    response.valid = false
    response.error = 'Settlement price is out of liquidation bounds, which is unsupported by a mutual early maturation'
    return response
  }
  const manager = new AnyHedgeManager()
  const outcome = await manager.calculateSettlementOutcome(
    contractData.parameters, contractData?.fundings?.[0]?.fundingSatoshis, settlementPrice);

  const expectedShortPayoutSats =  outcome.shortPayoutSatsSafe
  const expectedLongPayoutSats = outcome.longPayoutSatsSafe

  if (expectedShortPayoutSats !== mutualRedemptionData.shortSatoshis) {
    response.valid = false
    response.error = `short payout satoshis must be ${expectedShortPayoutSats}`
    return response
  }

  if (expectedLongPayoutSats !== mutualRedemptionData.longSatoshis) {
    response.valid = false
    response.error = `long payout satoshis must be ${expectedLongPayoutSats}`
    return response
  }

  response.valid = true
  return response
}


/**
 * 
 * @param {ContractData} contractData 
 * @param {MutualRedemptionData} mutualRedemptionData 
 */
export async function validateArbitraryRedemption(contractData, mutualRedemptionData) {
  const response = { valid: false, error: undefined, extraSats: 0 }

  // calculations from mutual refund & early maturation leave 1175 sats
  const txFee = contractData?.version?.includes?.('v0.11') ? 1175n : 1967n
  const fundingSats = contractData?.fundings?.[0]?.fundingSatoshis

  const valid = fundingSats >= mutualRedemptionData.shortSatoshis + mutualRedemptionData.longSatoshis + txFee
  response.extraSats = fundingSats - mutualRedemptionData.shortSatoshis + mutualRedemptionData.longSatoshis + txFee
  if (!valid) {
    response.valid = false
    response.error = `total payout satoshis exceeded ${fundingSats}, ${contractData?.fundings}`
    return response
  }

  response.valid = true
  return response
}


/**
 * @param {import('@generalprotocols/anyhedge').ContractData} contractData 
 * @param {MutualRedemptionData} mutualRedemptionData
 */
export async function completeMutualRedemption(contractData, mutualRedemptionData) {
  contractData = parseContractData(contractData)
  mutualRedemptionData.shortSatoshis = castBigIntSafe(mutualRedemptionData.shortSatoshis)
  mutualRedemptionData.longSatoshis = castBigIntSafe(mutualRedemptionData.longSatoshis)
  mutualRedemptionData.settlementPrice = castBigIntSafe(mutualRedemptionData.settlementPrice)

  const response = { success: false, settlementTxid: '', error: undefined }

  if (mutualRedemptionData.redemptionType === 'refund') {
    const mutualRefundValidation = await validateMutualRefund(contractData, mutualRedemptionData)
    if (!mutualRefundValidation.valid) {
      response.success = false
      response.error = mutualRefundValidation.error || 'Invalid mutual refund data'
      return response
    }
  } else if (mutualRedemptionData.redemptionType === 'early_maturation') {
    const earlyMaturationValidation = await validateEarlyMaturation(contractData, mutualRedemptionData)
    if (!earlyMaturationValidation.valid) {
      response.success = false
      response.error = earlyMaturationValidation.error || 'Invalid early maturation data'
      return response
    }
  }

  const arbitraryValidation = await validateArbitraryRedemption(contractData, mutualRedemptionData)
  if (!(await arbitraryValidation).valid) {
    response.success = false
    response.error = arbitraryValidation.error || 'Invalid redemption sats'
    return response 
  }

  const input = {
    txid: contractData?.fundings?.[0]?.fundingTransactionHash,
    vout: contractData?.fundings?.[0]?.fundingOutput,
    satoshis: contractData?.fundings?.[0]?.fundingSatoshis,
  }
  const shortOutput = { to: contractData?.metadata?.shortPayoutAddress, amount: mutualRedemptionData.shortSatoshis }
  const longOutput = { to: contractData?.metadata?.longPayoutAddress, amount: mutualRedemptionData.longSatoshis }

  const hedgeProposal = {
    inputs: [Object.assign({}, input)],
    outputs: [Object.assign({}, shortOutput), Object.assign({}, longOutput)],
    redemptionDataList: [{ 'short_key.schnorr_signature.all_outputs': mutualRedemptionData.shortSchnorrSig }]
  }
  const longProposal = {
    inputs: [Object.assign({}, input)],
    outputs: [Object.assign({}, shortOutput), Object.assign({}, longOutput)],
    redemptionDataList: [{ 'long_key.schnorr_signature.all_outputs': mutualRedemptionData.longSchnorrSig }]
  }

  const manager = new AnyHedgeManager()
  try {
    const txid = await manager.completeMutualRedemption(hedgeProposal, longProposal, contractData?.parameters)
    response.success = true
    response.settlementTxid = txid
    response.fundingTxid = input.txid
  } catch(error) {
    response.success = false
    response.error = 'encountered error in completing mutual redemption'
    if (error?.message) response.error = error?.message
    throw error
  }
  return response
}
