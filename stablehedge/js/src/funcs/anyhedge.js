import { getBaseBytecode, getContractParamBytecodes, parseContractData } from "../utils/anyhedge.js";
import { getLiquidityFee, getProxyFunderInputSize } from "../utils/anyhedge-funding.js";

/**
 * @param {Object} opts
 * @param {Object} opts.version
 */
export function getAnyhedgeBaseBytecode(opts) {
  return getBaseBytecode(opts)
}


/**
 * @param {import("@generalprotocols/anyhedge").ContractDataV2} contractData 
 * @returns 
 */
export async function prepareTreasuryContractParams(contractData) {
  contractData = parseContractData(contractData)
  return getContractParamBytecodes(contractData)
}


/**
 * 
 * @param {Object} opts
 * @param {import("@generalprotocols/anyhedge").ContractDataV2} opts.contractData
 * @returns 
 */
export async function getArgsForTreasuryContract(opts) {
  const contractData = parseContractData(opts?.contractData)

  const result = await prepareTreasuryContractParams(contractData)
  return { success: true, params: result }
}

/**
 * @param {Object} opts
 * @param {import("@generalprotocols/anyhedge").ContractDataV2} opts.contractData
 * @param {String} opts.anyhedgeVersion
 * @param {Number} opts.contributorNum
 * @returns 
 */
export async function calculateTotalFundingSatoshis(opts) {
  const contractData = parseContractData(opts?.contractData)
  let shortFundingSats = contractData?.metadata?.shortInputInSatoshis;
  let longFundingSats = contractData?.metadata?.longInputInSatoshis;

  // 1332 is DUST_LIMIT, when settlement prices for AH is at min/max
  // 798 is for settlement tx fee, added a few sats for margin
  // https://bitcoincashresearch.org/t/friday-night-challenge-worst-case-dust/1181/2
  // 1332 + 798 = 2130
  shortFundingSats += 2130n;

  const longLiquidityFee = getLiquidityFee(contractData)
  if (typeof longLiquidityFee === 'string') return { error: longLiquidityFee }
  if (longLiquidityFee) {
    shortFundingSats += longLiquidityFee.satoshis + 45n; // 45 is output fee
  }

  // This is calculated using getTreasuryContractInputSize in src/utils/anyhedge-funding.js
  // set to fixed since it's set in treasury contract's cashscript code
  const treasuryContractInputSize = 1025n;
  const shortFundingUtxoSats = shortFundingSats + treasuryContractInputSize;

  const proxyFunderInputSize = getProxyFunderInputSize(opts);

  // 10 sats as base tx details, 45 sats for p2sh32 output(no token)
  const longFundingUtxoSats = longFundingSats + BigInt(proxyFunderInputSize) + 10n + 45n;

  return {
    shortFundingSats,
    longFundingSats,
    treasuryContractInputSize,
    proxyFunderInputSize,
    shortFundingUtxoSats,
    longFundingUtxoSats,
  }
}
