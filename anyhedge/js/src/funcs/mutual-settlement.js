import { AnyHedgeManager, ContractData } from '@generalprotocols/anyhedge'

/**
 * @typedef {Object} RedemptionData
 * @property {String} [hedge_key.schnorr_signature.all_outputs]
 * @property {String} [long_key.schnorr_signature.all_outputs]
 * 
 * @typedef {Object} SignedTransactionProposal
 * @property {{ satoshis:Number, txid:String, vout:Number }} input
 * @property {{ amount:Number, to:String }} output
 * @property {RedemptionData[]} redemptionDataList
 * 
 * @typedef {Object} MutualRedemptionData
 * @property {'refund' | 'early_maturiation' | 'arbitrary'} redemptionType
 * @property {Number} hedgeSatoshis
 * @property {Number} longSatoshis
 * @property {String} hedgeSchnorrSig
 * @property {String} longSchnorrSig
 * @property {Number} [settlementPrice]
 */

/**
 * @param {ContractData} contractData 
 * @param {MutualRedemptionData} mutualRedemptionData
 */
export async function validateMutualRefund(contractData, mutualRedemptionData) {
  const response = { valid: false, error: undefined }

  if (contractData?.metadata?.hedgeInputSats !== mutualRedemptionData.hedgeSatoshis) {
    response.valid = false
    response.error = `hedge payout satoshis must be ${contractData?.metadata?.hedgeInputSats}`
    return response
  }

  if (contractData?.metadata?.longInputSats !== mutualRedemptionData.longSatoshis) {
    response.valid = false
    response.error = `long payout satoshis must be ${contractData?.metadata?.longInputSats}`
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
    contractData.parameters, contractData?.funding?.[0]?.fundingSatoshis, settlementPrice);

  const expectedHedgePayoutSats =  outcome.hedgePayoutSatsSafe
  const expectedLongPayoutSats = outcome.longPayoutSatsSafe

  if (expectedHedgePayoutSats !== mutualRedemptionData.hedgeSatoshis) {
    response.valid = false
    response.error = `hedge payout satoshis must be ${expectedHedgePayoutSats}`
    return response
  }

  if (expectedLongPayoutSats !== mutualRedemptionData.longSatoshis) {
    response.valid = false
    response.error = `hedge payout satoshis must be ${expectedLongPayoutSats}`
    return response
  }

  response.valid = true
  return response
}



/**
 * @param {ContractData} contractData 
 * @param {MutualRedemptionData} mutualRedemptionData
 */
export async function completeMutualRedemption(contractData, mutualRedemptionData) {
  const response = { success: false, settlementTxid: '', error: undefined }

  if (mutualRedemptionData.redemptionType === 'refund') {
    const mutualRefundValidation = await validateMutualRefund(contractData, mutualRedemptionData)
    if (!mutualRefundValidation.valid) {
      response.success = false
      response.error = mutualRefundValidation.error || 'Invalid mutual refund data'
      return response
    }
  } else if (mutualRedemptionData.redemptionType === 'early_maturiation') {
    const earlyMaturationValidation = await validateEarlyMaturation(contractData, mutualRedemptionData)
    if (!earlyMaturationValidation.valid) {
      response.success = false
      response.error = earlyMaturationValidation.error || 'Invalid early maturation data'
      return response
    }
  }

  const input = {
    txid: contractData?.funding?.[0]?.fundingTransaction,
    vout: contractData?.funding?.[0]?.fundingOutput,
    satoshis: contractData?.funding?.[0]?.fundingSatoshis,
  }
  const hedgeProposal = {
    inputs: [Object.assign({}, input)],
    outputs: [{ to: contractData?.metadata?.hedgeAddress, amount: mutualRedemptionData.hedgeSatoshis }],
    redemptionDataList: [{ 'hedge_key.schnorr_signature.all_outputs': mutualRedemptionData.hedgeSchnorrSig }]
  }
  const longProposal = {
    inputs: [Object.assign({}, input)],
    outputs: [{ to: contractData?.metadata?.longAddress, amount: mutualRedemptionData.longSatoshis }],
    redemptionDataList: [{ 'long_key.schnorr_signature.all_outputs': mutualRedemptionData.longSchnorrSig }]
  }

  const manager = new AnyHedgeManager()
  try {
    const txid = await manager.completeMutualRedemption(hedgeProposal, longProposal, contract?.parameters)
    response.success = true
    response.settlementTxid = txid
  } catch(error) {
    response.success = false
    response.error = 'encountered error in completing mutual redemption'
    if (error?.message) response.error = error?.message
  }
  return response
}
