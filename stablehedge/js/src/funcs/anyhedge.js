import { getBaseBytecode, parseContractData } from "../utils/anyhedge.js";
import { getLiquidityFee, getSettlementServiceFee, getProxyFunderInputSize } from "../utils/anyhedge-funding.js";

/**
 * @param {Object} opts
 * @param {Object} opts.version
 */
export function getAnyhedgeBaseBytecode(opts) {
  return getBaseBytecode(opts)
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

  const settlementTxFee = 2030n;
  // 1332 is DUST_LIMIT, when settlement prices for AH is at min/max
  // 798 is for settlement tx fee, added a few sats for margin
  // https://bitcoincashresearch.org/t/friday-night-challenge-worst-case-dust/1181/2
  // 1332 + 698 = 2130
  shortFundingSats += settlementTxFee;
  const fundingOutputSats = shortFundingSats + longFundingSats;

  const longLiquidityFee = getLiquidityFee(contractData)
  if (typeof longLiquidityFee === 'string') return { error: longLiquidityFee }
  if (longLiquidityFee) {
    shortFundingSats += longLiquidityFee.satoshis + 45n; // 45 is output fee
  }

  const settlementServiceFee = getSettlementServiceFee(contractData)
  if (typeof settlementServiceFee === 'string') return { error: settlementServiceFee }
  if (settlementServiceFee) {
    shortFundingSats += settlementServiceFee.satoshis + 45n; // 45 is output fee
  }

  // This is calculated using getTreasuryContractInputSize in src/utils/anyhedge-funding.js
  // set to fixed since it's set in treasury contract's cashscript code
  const treasuryContractInputSize = 1100n;
  const shortFundingUtxoSats = shortFundingSats + treasuryContractInputSize;

  const proxyFunderInputSize = getProxyFunderInputSize(opts);

  // 10 sats as base tx details, 45 sats for p2sh32 output(no token)
  const longFundingUtxoSats = longFundingSats + BigInt(proxyFunderInputSize) + 10n + 45n;

  const totalFundingSats = contractData?.parameters.payoutSats + settlementTxFee;

  return {
    fundingOutputSats,
    shortFundingSats,
    longFundingSats,
    treasuryContractInputSize,
    proxyFunderInputSize,
    shortFundingUtxoSats,
    longFundingUtxoSats,
    totalFundingSats,
  }
}
