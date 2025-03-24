import { hexToBin } from "@bitauth/libauth";
import { getContractParamBytecodes } from "./anyhedge.js";

import { calculateInputSize } from "./transaction.js";
import { createProxyFunder, createTreasuryContract } from "./factory.js";

/**
 * @param {Object} opts
 * @param {import("@generalprotocols/anyhedge").ContractDataV2} opts.contractData
 * @param {String} opts.anyhedgeVersion
 */
export function getTreasuryContractInputSize(opts) {
  const { contract } = createTreasuryContract(opts)

  const ahContract = opts?.contractData
  const ahContractArgs = getContractParamBytecodes(ahContract)
  const treasuryContractInputSize = calculateInputSize(contract.functions.spendToAnyhedge(
    hexToBin(ahContractArgs.segment1),
    hexToBin(ahContractArgs.segment2),
    ahContractArgs.longLockScript,
    ahContract.metadata.shortInputInSatoshis,
    ahContract.metadata.longInputInSatoshis,
    hexToBin(ahContractArgs.lowPrice),
    hexToBin(ahContractArgs.highPrice),
    hexToBin(ahContractArgs.startTs),
    hexToBin(ahContractArgs.maturityTs),
    ahContract.fees?.[0] ? ahContract.fees[0].satoshis : 0n,
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
  if (contractData.fees.length > 1) return 'Must only have atmost 1 fee'

  const fee = contractData.fees[0]
  if (fee.address !== contractData.metadata.longPayoutAddress) {
    return 'Fee recipient must be long payout address'
  }

  const MIN_FEE = 546;
  const MAX_FEE = contractData.metadata.shortInputInSatoshis / 20; // ~5%
  const feeSats = fee.satoshis

  if (feeSats < MIN_FEE || feeSats > MAX_FEE) return 'Invalid fee amount'

  return fee
}

