import { AnyHedgeArtifacts } from "@generalprotocols/anyhedge-contracts";
import { asmToScript, generateRedeemScript, scriptToBytecode } from "@cashscript/utils"
import { encodeConstructorArguments } from "cashscript/dist/Argument.js";
import { binToHex } from "@bitauth/libauth";

/**
 * @param {Object} opts
 * @param {String} opts.version
 */
export function getArtifact(opts) {
  let version = opts?.version
  if (version === undefined || version === null) {
    version = "AnyHedge v0.12"
  }

  const artifact = AnyHedgeArtifacts[version]
  return { artifact, version }
}


/**
 * @param {Object} opts
 * @param {String} opts.version
 */
export function getBaseBytecode(opts) {
  const { artifact, version } = getArtifact(opts)

  const script = asmToScript(artifact.bytecode)
  const baseScript = generateRedeemScript(script, new Uint8Array())  

  const baseBytecode = scriptToBytecode(baseScript)

  return { bytecode: binToHex(baseBytecode), version: version }
}

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

/**
 * @param {import("@generalprotocols/anyhedge").ContractDataV2} contractData 
 * @returns 
 */
export function getContractParamBytecodes(contractData) {
  const contractParameters = contractData.parameters
  const parameters = [
    contractParameters.shortMutualRedeemPublicKey,
    contractParameters.longMutualRedeemPublicKey,
    contractParameters.enableMutualRedemption,
    contractParameters.shortLockScript,
    contractParameters.longLockScript,
    contractParameters.oraclePublicKey,
    contractParameters.nominalUnitsXSatsPerBch,
    contractParameters.satsForNominalUnitsAtHighLiquidation,
    contractParameters.payoutSats,
    contractParameters.lowLiquidationPrice,
    contractParameters.highLiquidationPrice,
    contractParameters.startTimestamp,
    contractParameters.maturityTimestamp,
  ];

  const { artifact } = getArtifact({ version: contractData.version })
  const encodedArgs = encodeConstructorArguments(artifact, parameters).slice();
  const argsScript = generateRedeemScript(new Uint8Array(), encodedArgs);
  const bytecodesHex = argsScript.map(script => {
    return binToHex(scriptToBytecode([script]))
  })

  // const argsCount = bytecodesHex.length
  const segment1 = bytecodesHex.slice(3).reverse().join('');
  const segment2 = bytecodesHex.slice(5, 8).reverse().join('');

  return {
    segment1,
    segment2,
    bytecodesHex,
    shortMutualRedeemPublicKey: bytecodesHex[12],
    longMutualRedeemPublicKey: bytecodesHex[11],
    enableMutualRedemption: bytecodesHex[10],
    shortLockScript: bytecodesHex[9],
    longLockScript: bytecodesHex[8],
    oraclePublicKey: bytecodesHex[7],
    nominalUnitsXSatsPerBch: bytecodesHex[6],
    satsForNominalUnitsAtHighLiquidation: bytecodesHex[5],
    payoutSats: bytecodesHex[4],
    lowPrice: bytecodesHex[3],
    highPrice: bytecodesHex[2],
    startTs: bytecodesHex[1],
    maturityTs: bytecodesHex[0],
  }
}
