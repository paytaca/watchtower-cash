import axios from 'axios'
import { AnyHedgeManager } from '@generalprotocols/anyhedge'
import { getPriceMessages } from './price.js'
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
  const _hedgeNominalUnitSats = hedgePositionOffer.satoshis * assetPrice
  const  hedgeNominalUnits = _hedgeNominalUnitSats / 10 ** 8
  const lowLiquidationPrice = Math.round(assetPrice * hedgePositionOffer.lowLiquidationMultiplier)
  const totalSats = Math.round(_hedgeNominalUnitSats / lowLiquidationPrice)
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
 * @param {Object} constraints
 */
export async function checkLiquidityProviderConstraints(hedgePositionOffer, priceData, constraints) {
  const response = { valid: true, error: '' }
  const { hedgeNominalUnits } = calculateHedgePositionOfferInputs(hedgePositionOffer, priceData.priceValue)
  const durationSeconds = hedgePositionOffer.durationSeconds
  const lowLiquidationMultiplier = hedgePositionOffer.lowLiquidationMultiplier

  if (!constraints) {
    response.valid = false
    response.error = 'Constraints not found'
    return
  }

  const withinNominalRange = constraints.minimumNominalUnits <= hedgeNominalUnits && constraints.maximumNominalUnits >= hedgeNominalUnits
  if (!withinNominalRange){
    response.valid = false
    response.error = `Nominal units ${hedgeNominalUnits} outside (${constraints.minimumNominalUnits}, ${constraints.maximumNominalUnits})`
    return response
  }
  const withinDurationRange = constraints.minimumDuration <= durationSeconds && constraints.maximumDuration >= durationSeconds
  if (!withinDurationRange) {
    response.valid = false
    response.error = `Duration ${durationSeconds} outside (${constraints.minimumDuration}, ${constraints.maximumDuration})`
    return response
  }

  const withinLiquidationRange = constraints.minimumLiquidationLimit <= lowLiquidationMultiplier && constraints.maximumLiquidationLimit >= lowLiquidationMultiplier
  if (withinLiquidationRange) {
    response.valid = false
    response.error = `Liquidation limit ${lowLiquidationMultiplier} outside (${constraints.minimumLiquidationLimit}, ${constraints.maximumLiquidationLimit})`
    return response 
  }

  return response
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
  const requestData = { oraclePublicKey: priceData.oraclePubKey, poolSide: 'hedge' }
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
 * @param {Object} contractCreationParameters 
 * @param {Number} contractStartingOracleMessageSequence 
 * @returns 
 */
export async function proposeContract(contractCreationParameters, contractStartingOracleMessageSequence) {
  const response = {
    success: false,
    error: '',
    liquidityFees: {
      liquidityProviderFeeInSatoshis: 0,
      renegotiateAfterTimestamp: 0,
    },
  }
  const requestData = { contractCreationParameters, contractStartingOracleMessageSequence }
  const { data } = await backend.post('/api/v1/proposeContract', requestData)

  response.success = true
  response.liquidityFees.liquidityProviderFeeInSatoshis = data.liquidityProviderFeeInSatoshis
  response.liquidityFees.renegotiateAfterTimestamp = data.renegotiateAfterTimestamp
  return response
}


/**
 * 
 * @param {HedgePositionOffer} hedgePositionOffer 
 * @param {PriceMessageConfig | undefined } priceMessageConfig
 * @param {PriceRequestParams | undefined } priceMessageRequestParams
 */
export async function matchHedgePositionOffer(hedgePositionOffer, priceMessageConfig, priceMessageRequestParams) {
  const response = {
    success: false,
    error: '',
    contractData: {},
    contractCreationParameters: {},
    liquidityFees: {},
    settlementService: {},
    oracleRelay: {},
    oracleMessageSequence: 0
  }

  const liquidityServiceInfo = await getLiquidityServiceInfo()
  if (liquidityServiceInfo?.oracleRelay) response.oracleRelay = liquidityServiceInfo?.oracleRelay
  if (liquidityServiceInfo?.settlementService) response.settlementService = liquidityServiceInfo?.settlementService

  const _priceMessageConfig = Object.assign({}, priceMessageConfig)
  if (liquidityServiceInfo?.oracleRelay?.host) {
    _priceMessageConfig.oracleRelay = liquidityServiceInfo?.oracleRelay?.host
    // _priceMessageConfig.oracleRelayPort = liquidityServiceInfo?.oracleRelay?.port
  }

  const priceMessagesResponse = await getPriceMessages(_priceMessageConfig, priceMessageRequestParams)
  const priceData = priceMessagesResponse?.results?.[0]?.priceData
  if (!priceData) throw 'Unable to retrieve price data'
  response.oracleMessageSequence = priceData.messageSequence


  const constraints = liquidityServiceInfo?.liquidityParameters?.[priceData.oraclePubKey]?.long
  if (!constraints) {
    response.success = false
    response.error = 'Liquidity provider constraints not found'
    return response
  }

  const lpConstraintsCheck = await checkLiquidityProviderConstraints(hedgePositionOffer, priceData, constraints)
  if (!lpConstraintsCheck.valid) {
    response.success = false
    response.error = lpConstraintsCheck.error || 'hedge position offer outside liquidity provider\'s constraints'
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
  const contractProposalResponse = await proposeContract(contractCreationParameters, priceData.messageSequence)
  if (!contractProposalResponse.success) {
    response.success = false
    response.error = contractProposalResponse.error || 'Error proposing hedge position'
    return response
  }

  response.liquidityFees = contractProposalResponse.liquidityFees

  const contractData = await compileContract(contractCreationParameters)
  response.success = true
  response.contractData = contractData
  response.contractCreationParameters = contractCreationParameters

  return response
}

/**
 * 
 * @param {Object} contractData 
 * @param {FundingProposal} fundingProposal 
 * @param {Number} oracleMessageSequence 
 */
export async function fundHedgePosition(contractData, fundingProposal, oracleMessageSequence) {
  const response = { success: false, fundingTransactionHash: '', error: '' }
  const fundContractData = {
    contractAddress: response.contractData.address,
    outpointTransactionHash: fundingProposal.txHash,
    outpointIndex: fundingProposal.txIndex,
    satoshis: fundingProposal.txValue,
    signature: fundingProposal.scriptSig,
    publicKey: fundingProposal.publicKey,
    takerSide: 'hedge', // hedge | long
    dependencyTransactions: fundingProposal.inputTxHashes,
    oracleMessageSequence: oracleMessageSequence,
  }

  const input = contractData?.metadata?.hedgeInputSats
  const fees = contractData?.fees?.satoshis
  const expectedFundingSats = input + fees
  if (fundingProposal.txValue !== expectedFundingSats) {
    response.success = false
    response.error = `Funding proposal satoshis must be ${input}+ ${fees}, got ${fundingProposal.txValue}`
    return response
  }

  try {
    const fundContractResponse = await backend.post('/api/v1/fundContract', fundContractData)
    // https://gitlab.com/GeneralProtocols/anyhedge/library/-/blob/development/lib/interfaces/liquidity-provider.ts#L147
    response.fundingTransactionHash = fundContractResponse.data.fundingTransactionHash
    response.success = true
  } catch(error) {
    response.success = false
    response.error = error
  }

  return response
}

/**
 * 
 * @param {HedgePositionOffer} hedgePositionOffer 
 * @param {FundingProposal} fundingProposal
 * @param {PriceMessageConfig | undefined } priceMessageConfig
 * @param {PriceRequestParams | undefined } priceMessageRequestParams 
 */
export async function matchAndFundHedgePositionOffer(hedgePositionOffer, fundingProposal, priceMessageConfig, priceMessageRequestParams)  {
  const response = await matchHedgePositionOffer(hedgePositionOffer, priceMessageConfig, priceMessageRequestParams)
  if (!response.success) return response

  const _managerConfig = {
    serviceScheme: response.settlementService.scheme,
    serviceDomain: response.settlementService.host,
    servicePort: response.settlementService.port,
  }
  const manager = new AnyHedgeManager(_managerConfig);
  const authenticationToken = await manager.requestAuthenticationToken('Paytaca')
  _managerConfig.authenticationToken = authenticationToken
  const managerWithAuthToken = new AnyHedgeManager(_managerConfig);
  response.contractData = await managerWithAuthToken.getContractStatus(response.contractData.address);

  const fundingResponse = await fundHedgePosition(response.contractData, fundingProposal, response.oracleMessageSequence)
  if (!fundingResponse.success) {
    response.success = false
    response.error = fundingResponse?.error || 'Error encountered in funding contract'
  } else {
    response.success = true
    response.fundingTransactionHash = fundingResponse.fundingTransactionHash
  }

  return response
}
