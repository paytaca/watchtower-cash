import axios from 'axios'
import { getPriceData } from './price.js'
import { compileContract } from './create.js'

/**
 * @typedef HedgePositionOffer
 * @property {Number} satoshis
 * @property {Number} durationSeconds
 * @property {Number} lowLiquidationMultiplier
 * @property {Number} highLiquidationMultiplier
 * @property {String} hedgeAddress
 * @property {String} hedgePubkey
 * 
 * @typedef FundingProposal
 * @property {String} txHash - The transaction hash of the Outpoint (UTXO) being spent.
 * @property {Number} txIndex - The index of the Outpoint (UTXO) being spent.
 * @property {Number} txValue - The satoshis locked in the Outpoint (UTXO).
 * @property {String} scriptSig - The signature to provide to the Liquidity Provider so that the Contract can be funded.
 * @property {String} publicKey - The public key that corresponds to the signature. (TODO: unsure where to retrieve this)
 * @property {String[]} inputTxHashes - Array of transaction hashes that the outpoint depends upon.
 */

const BASE_URL = 'https://staging-liquidity.anyhedge.com'

const backend = axios.create({
  baseURL: BASE_URL,
})

/**
 * 
 * @param {HedgePositionOffer} hedgePositionOffer 
 * @param {Number} assetPrice 
 */
function calculateHedgePositionOfferInputs(hedgePositionOffer, assetPrice) {
  const hedgeNominalUnits = hedgePositionOffer.satoshis * assetPrice
  const lowLiquidationPrice = Math.round(assetPrice * hedgePositionOffer.lowLiquidationMultiplier)
  const totalSats = Math.round(hedgeNominalUnits / lowLiquidationPrice)
  const longSats = totalSats - hedgePositionOffer.satoshis
  const longNominalUnits = (longSats * assetPrice) / 10 ** 8

  return {
    hedgeNominalUnits,
    longNominalUnits,
    hedgeSats: hedgePositionOffer.satoshis,
    longSats,
    totalSats,
  }
}

export async function getLiquidityServiceInfo() {
  const response = await backend.get('/api/v1/liquidityServiceInformation')
  return response.data
}

/**
 * 
 * @param {HedgePositionOffer} hedgePositionOffer 
 * @param {{ priceValue: Number, oraclePubKey: String }} priceData
 */
export async function checkLiquidityProviderConstraints(hedgePositionOffer, priceData) {
  const { longNominalUnits } = calculateHedgePositionOfferInputs(hedgePositionOffer, priceData.priceValue)
  const durationSeconds = hedgePositionOffer.durationSeconds
  const lowLiquidationMultiplier = hedgePositionOffer.lowLiquidationMultiplier

  const liquidityServiceInfo = await getLiquidityServiceInfo()
  const constraints = liquidityServiceInfo?.liquidityParameters?.[priceData.oraclePubKey]?.long
  if (!constraints) return undefined
  
  if (constraints.minimumNominalUnits > longNominalUnits || constraints.maximumNominalUnits < longNominalUnits) return false
  if (constraints.minimumDuration > durationSeconds || constraints.maximumDuration < durationSeconds) return false
  if (constraints.minimumLiquidationLimit > lowLiquidationMultiplier || constraints.maximumLiquidationLimit < lowLiquidationMultiplier) return false

  return true
}


/**
 * 
 * @param {HedgePositionOffer} hedgePositionOffer 
 * @param {{ priceValue: Number, oraclePubKey: String }} priceData
 */
export async function prepareContractPosition(hedgePositionOffer, priceData) {
  const response = {
    valid: false,
    error: '',
    details: {
      availableLiquidity: 0,
      liquidityProvidersMutualRedemptionPublicKey: '',
      liquidityProvidersPayoutAddress: '',
    }
  }
  const requestData = { oraclePubkey: priceData.oraclePubKey }
  const { data } = await backend.post('/api/v1/prepareContractPosition', requestData)

  const { longSats } = calculateHedgePositionOfferInputs(hedgePositionOffer, priceData.priceValue)
  if (data.availableLiquidity < longSats) {
    response.valid = false
    response.error = 'Not enough balance in liquidity pool'
    return response
  }

  response.valid = true
  response.details = data
  return response
}


/**
 * 
 * @param {HedgePositionOffer} hedgePositionOffer 
 */
export async function matchHedgePositionOffer(hedgePositionOffer) {
  const response = { success: false, error: '', contractData: {} }

  const priceData = await getPriceData()

  const lpConstraintsValid = await checkLiquidityProviderConstraints(hedgePositionOffer, priceData)
  if (!lpConstraintsValid) {
    response.success = false
    response.error = 'hedge position offer outside liquidity provider\'s constraints'
    return response
  }

  const longPosition = await prepareContractPosition(hedgePositionOffer, priceData)
  if (!longPosition.valid) {
    response.success = false
    response.error = longPosition.error || 'Unable to prepare contract position'
    return response
  }

  const hedgePositionOfferInputs = calculateHedgePositionOfferInputs(hedgePositionOffer, priceData.priceValue)

  const contractCreationParameters = {
    nominalUnits: hedgePositionOfferInputs.hedgeNominalUnits,
    duration: hedgePositionOffer.durationSeconds,
    startPrice: priceData.priceValue,
    startTimestamp: priceData.messageTimestamp,
    oraclePublicKey: priceData.oraclePubKey,
    highLiquidationPriceMultiplier: hedgePositionOffer.highLiquidationMultiplier,
    lowLiquidationPriceMultiplier: hedgePositionOffer.lowLiquidationMultiplier,
    hedgePublicKey: hedgePositionOffer.hedgePubkey,
    longPublicKey: longPosition.details.liquidityProvidersMutualRedemptionPublicKey,
    hedgeAddress: hedgePositionOffer.hedgeAddress,
    longAddress: longPosition.details.liquidityProvidersPayoutAddress,
  }

  const contractData = await compileContract(contractCreationParameters)
  response.success = true
  response.contractData = contractData

  return response
}

/**
 * 
 * @param {HedgePositionOffer} hedgePositionOffer 
 * @param {FundingProposal} fundingProposal 
 */
export async function matchAndFundHedgePositionOffer(hedgePositionOffer, fundingProposal)  {
  const response = await matchHedgePositionOffer(hedgePositionOffer)
  if (!response.success) return response

  const fundContractData = {
    contractAddress: response.contractData.address,
    outpointTransactionHash: fundingProposal.txHash,
    outpointIndex: fundingProposal.txIndex,
    satoshis: fundingProposal.txValue,
    signature: fundingProposal.scriptSig,
    publicKey: fundingProposal.publicKey,
    takerSide: 'hedge', // hedge | long
    dependencyTransactions: fundingProposal.inputTxHashes,
  }

  const fundContractResponse = await backend.post('/api/v1/fundContract', fundContractData)

  response.fundingContract = fundContractResponse.data
  return response 
}
