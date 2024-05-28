export function castBigInt(value, radix) {
  try {
    return BigInt(value)
  } catch (error) {
    return BigInt(parseInt(value, radix))
  }
}


export function castBigIntSafe(value, radix) {
  try { return castBigInt(value, radix) } catch { }
  return value
}

/**
 * @param {Object} contractCreationParameters
 * @param {'short' | 'long'} contractCreationParameters.takerSide
 * @param {'short' | 'long'} contractCreationParameters.makerSide
 * @param {Number} contractCreationParameters.nominalUnits - US cents
 * @param {String} contractCreationParameters.oraclePublicKey
 * @param {String} contractCreationParameters.startingOracleMessage
 * @param {String} contractCreationParameters.startingOracleSignature
 * @param {Number} contractCreationParameters.maturityTimestamp
 * @param {Number} contractCreationParameters.highLiquidationPriceMultiplier
 * @param {Number} contractCreationParameters.lowLiquidationPriceMultiplier
 * @param {String} contractCreationParameters.shortMutualRedeemPublicKey
 * @param {String} contractCreationParameters.longMutualRedeemPublicKey
 * @param {String} contractCreationParameters.shortPayoutAddress
 * @param {String} contractCreationParameters.longPayoutAddress
 * @param {0 | 1} contractCreationParameters.enableMutualRedemption
 * @param {0 | 1} contractCreationParameters.isSimpleHedge
 */
export function transformContractCreationParamsV2toV1(contractCreationParameters) {
  const response = Object.assign({}, contractCreationParameters)

  if (response?.takerSide === 'short') response.takerSide = 'hedge'
  if (response?.makerSide === 'short') response.makerSide = 'hedge'
  response.maturityTimestamp = parseInt(response?.maturityTimestamp)
  response.enableMutualRedemption = parseInt(response?.enableMutualRedemption)
  response.hedgeMutualRedeemPublicKey = response?.shortMutualRedeemPublicKey
  response.hedgePayoutAddress = response?.shortPayoutAddress

  response.shortMutualRedeemPublicKey = undefined
  response.shortPayoutAddress = undefined
  response.isSimpleHedge = undefined
  return response
}


export function parseContractCreationParamsV2(contractCreationParameters) {
  const contractCreationParametersV2 = Object.assign({} , contractCreationParameters);
  contractCreationParametersV2.maturityTimestamp = castBigIntSafe(contractCreationParametersV2.maturityTimestamp)
  contractCreationParametersV2.enableMutualRedemption = castBigIntSafe(contractCreationParametersV2.enableMutualRedemption) 
  contractCreationParametersV2.isSimpleHedge = castBigIntSafe(contractCreationParametersV2.isSimpleHedge)
  return contractCreationParametersV2
}

/**
 * @param {import('@generalprotocols/anyhedge').ContractDataV2} contractDataV2 
 */
export function parseContractData(contractDataV2) {
  if (!contractDataV2?.parameters) return contractDataV2
  if (!contractDataV2?.metadata) return contractDataV2

  contractDataV2.parameters.maturityTimestamp = castBigIntSafe(contractDataV2.parameters.maturityTimestamp)
  contractDataV2.parameters.startTimestamp = castBigIntSafe(contractDataV2.parameters.startTimestamp)
  contractDataV2.parameters.highLiquidationPrice = castBigIntSafe(contractDataV2.parameters.highLiquidationPrice)
  contractDataV2.parameters.lowLiquidationPrice = castBigIntSafe(contractDataV2.parameters.lowLiquidationPrice)
  contractDataV2.parameters.payoutSats = castBigIntSafe(contractDataV2.parameters.payoutSats)
  contractDataV2.parameters.nominalUnitsXSatsPerBch = castBigIntSafe(contractDataV2.parameters.nominalUnitsXSatsPerBch)
  contractDataV2.parameters.satsForNominalUnitsAtHighLiquidation = castBigIntSafe(contractDataV2.parameters.satsForNominalUnitsAtHighLiquidation)
  contractDataV2.parameters.enableMutualRedemption = castBigIntSafe(contractDataV2.parameters.enableMutualRedemption)

  contractDataV2.metadata.durationInSeconds = castBigIntSafe(contractDataV2.metadata.durationInSeconds)
  contractDataV2.metadata.startPrice = castBigIntSafe(contractDataV2.metadata.startPrice)
  contractDataV2.metadata.longInputInSatoshis = castBigIntSafe(contractDataV2.metadata.longInputInSatoshis)
  contractDataV2.metadata.shortInputInSatoshis = castBigIntSafe(contractDataV2.metadata.shortInputInSatoshis)
  contractDataV2.metadata.minerCostInSatoshis = castBigIntSafe(contractDataV2.metadata.minerCostInSatoshis)
  contractDataV2.metadata.isSimpleHedge = castBigIntSafe(contractDataV2.metadata.isSimpleHedge)

  if (Array.isArray(contractDataV2.fees)) {
    contractDataV2.fees = contractDataV2.fees.map(fee => {
      if (!fee) return fee
      fee.satoshis = castBigIntSafe(fee.satoshis)
      return fee
    })
  }

  if (Array.isArray(contractDataV2.fundings)) {
    contractDataV2.fundings = contractDataV2.fundings.map(funding => {
      if (!funding) return funding
      funding.fundingOutputIndex = castBigIntSafe(funding.fundingOutputIndex)
      funding.fundingSatoshis = castBigIntSafe(funding.fundingSatoshis)

      if (!funding.settlement) return funding
      funding.settlement.shortPayoutInSatoshis = castBigIntSafe(funding.settlement.shortPayoutInSatoshis)
      funding.settlement.longPayoutInSatoshis = castBigIntSafe(funding.settlement.longPayoutInSatoshis)
      funding.settlement.settlementPrice = castBigIntSafe(funding.settlement.settlementPrice)
      return funding
    })
  }

  return contractDataV2
}