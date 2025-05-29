import { hexToBin, isHex } from "@bitauth/libauth";
import { getBaseBytecode, getContractParamBytecodes } from "./anyhedge.js";

import { calculateInputSize } from "./transaction.js";
import { createProxyFunder, createTreasuryContract } from "./factory.js";
import { baseBytecodeToHex, encodeParameterBytecode } from "./contracts.js";


const LP_FEE_NAME = 'Liquidity Premium'
const SETTLEMENT_SERVICE_FEE_NAME = 'Settlement Service Fee'

/**
 * @param {Object} opts
 * @param {import("@generalprotocols/anyhedge").ContractDataV2} opts.contractData
 * @param {String} opts.anyhedgeVersion
 */
export function getTreasuryContractInputSize(opts) {
  const { contract } = createTreasuryContract(opts)
  const treasuryContractInputSize = calculateInputSize(contract.functions.spendToAnyhedge(
    ...prepareParamForTreasuryContract(ahContract),
  ))
  return treasuryContractInputSize
}


/**
 * @param {Object} opts 
 * @param {import("@generalprotocols/anyhedge").ContractDataV2} opts.contractData
 * @param {String} opts.anyhedgeVersion
 */
export function getProxyFunderInputSize(opts) {
  const { contract } = createProxyFunder(opts)
  const ahContract = opts?.contractData
  const ahContractArgs = getContractParamBytecodes(ahContract)
  
  const proxyFunderInputSize = calculateInputSize(contract.functions.spendToContract(
    hexToBin(ahContractArgs.bytecodesHex.slice(0, 4).reverse().join('')),
    hexToBin(ahContractArgs.bytecodesHex.slice(5).reverse().join('')),
  ))

  return proxyFunderInputSize
}

/**
 * @param {import("@generalprotocols/anyhedge").ContractDataV2} contractData 
 */
export function getLiquidityFee(contractData) {
  if (!contractData.fees.length) return
  if (contractData.fees.length > 2) return 'Must only have atmost 2 fee'

  const fee = contractData.fees.find(fee => fee.name === LP_FEE_NAME)
  if (!fee) return
  if (fee.address !== contractData.metadata.longPayoutAddress) {
    return 'Fee recipient must be long payout address'
  }

  const MIN_FEE = 546;
  const MAX_FEE = contractData.metadata.shortInputInSatoshis / 20n; // ~5%
  const feeSats = fee.satoshis

  if (feeSats < MIN_FEE || feeSats > MAX_FEE) return 'Invalid fee amount'

  return fee
}


/**
 * @param {import("@generalprotocols/anyhedge").ContractDataV2} contractData 
 */
export function getSettlementServiceFee(contractData) {
  if (!contractData.fees.length) return
  if (contractData.fees.length > 2) return 'Must only have atmost 2 fee'

  const fee = contractData.fees.find(fee => fee.name === SETTLEMENT_SERVICE_FEE_NAME)
  if (!fee) return

  const MIN_FEE = 546;
  const MAX_FEE = (contractData.parameters.payoutSats * 75n + 9999n) / 10000n; // ~0.5%
  const feeSats = fee.satoshis

  if (feeSats < MIN_FEE || feeSats > MAX_FEE) return 'Invalid fee amount'

  return fee
}


/**
 * @param {import("@generalprotocols/anyhedge").ContractDataV2} contractData 
 * @param {Object} opts
 * @param {String} [opts.contractBaseBytecode]
 * @param {String} [opts.treasuryContractVersion]
 */
export function prepareParamForTreasuryContract(contractData, opts) {
  const _bytecodes = getContractParamBytecodes(contractData)
  const {
      bytecodesHex,
      shortMutualRedeemPublicKey,
      longLockScript,
      nominalUnitsXSatsPerBch,
      satsForNominalUnitsAtHighLiquidation,
      lowPrice,
      highPrice,
      startTs,
      maturityTs,
    } = _bytecodes
    const fee = getLiquidityFee(contractData);
    const settlementServiceFee = getSettlementServiceFee(contractData);

    let contractBaseBytecode = opts?.contractBaseBytecode
    if (!contractBaseBytecode) {
      const { bytecode } = getBaseBytecode({ version: contractData.version })
      contractBaseBytecode = bytecode;
    }

    const param5 = opts?.treasuryContractVersion === 'v3'
      ? hexToBin(nominalUnitsXSatsPerBch)
      : hexToBin(bytecodesHex.slice(5, 7).reverse().join(''))
    return [
      isHex(contractBaseBytecode) ? hexToBin(contractBaseBytecode) : contractBaseBytecode,
      shortMutualRedeemPublicKey,
      hexToBin(bytecodesHex.slice(1, 3).reverse().join('')),
      hexToBin(longLockScript),
      param5,
      satsForNominalUnitsAtHighLiquidation,
      contractData.metadata.shortInputInSatoshis,
      contractData.metadata.longInputInSatoshis,
      hexToBin(lowPrice),
      hexToBin(highPrice),
      hexToBin(startTs),
      hexToBin(maturityTs),
      fee?.satoshis ? fee.satoshis : 0n,
      settlementServiceFee?.satoshis ? settlementServiceFee.satoshis : 0n,
    ]
}

/**
 * @param {import("@generalprotocols/anyhedge").ContractDataV2} contractData 
 */
export function prepareParamForProxyFunder(contractData) {
  const { bytecodesHex } = getContractParamBytecodes(contractData)
  return [
    hexToBin(bytecodesHex.slice(0, 4).reverse().join('')),
    hexToBin(bytecodesHex.slice(5).reverse().join('')),
  ]
}

/**
 * @param {import("cashscript").Artifact} artifact
 * @param {any[]} parameters
 * @param {Number} contributorIndex
 */
export function prepareParamForLP(artifact, parameters, contributorIndex) {
  const parameterBytecodes = encodeParameterBytecode(artifact, parameters)
  
  const segment1 = parameterBytecodes.slice(2 + contributorIndex);
  const segment2 = parameterBytecodes.slice(0, 1 + contributorIndex);
  const baseBytecode = baseBytecodeToHex(artifact.bytecode);

  console.log('Bytecodes', parameterBytecodes)
  console.log('Parambytecode', [...parameterBytecodes].reverse().join(''));
  console.log('Segment1', [...segment1].reverse().join(''));
  console.log('Segment2', [...segment2].reverse().join(''));

  return [
    hexToBin(segment1.reverse().join('')),
    hexToBin(segment2.reverse().join('')),
    hexToBin(baseBytecode),
  ]
}