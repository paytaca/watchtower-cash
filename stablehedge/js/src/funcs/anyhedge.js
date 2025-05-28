import { getBaseBytecode, parseContractData } from "../utils/anyhedge.js";
import { getLiquidityFee, getSettlementServiceFee, getProxyFunderInputSize } from "../utils/anyhedge-funding.js";
import { P2PKH_INPUT_SIZE } from "cashscript/dist/constants.js";

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
 * @param {Number} [opts.contributorNum] Set to 0 to assume p2pkh counterparty instead of P2P-LP contract
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

  let longFundingUtxoSats = longFundingSats + BigInt(P2PKH_INPUT_SIZE) + 35n; // 34 is p2pkh output fee
  if (opts?.contributorNum) {
    const proxyFunderInputSize = getProxyFunderInputSize(opts);
    // 45 sats for p2sh32 output(no token)
    longFundingUtxoSats = longFundingSats + BigInt(proxyFunderInputSize) + 45n;
  }

  const totalFundingSats = contractData?.parameters.payoutSats + settlementTxFee;

  return {
    fundingOutputSats,
    shortFundingSats,
    longFundingSats,
    treasuryContractInputSize,
    shortFundingUtxoSats,
    longFundingUtxoSats,
    totalFundingSats,
  }
}
