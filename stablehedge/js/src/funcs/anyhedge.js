import { getBaseBytecode, parseContractData } from "../utils/anyhedge.js";
import { getLiquidityFee, getSettlementServiceFee, getAnyhedgeSettlementTxFeeSize, getTreasuryContractInputSize, getFeeSats } from "../utils/anyhedge-funding.js";
import { cashAddressToLockingBytecode } from "@bitauth/libauth";
import { TreasuryContract } from "../contracts/treasury-contract/index.js";
import { AnyHedgeManager } from "@generalprotocols/anyhedge";
import { constructFundingOutputs } from "@generalprotocols/anyhedge/build/lib/util/funding-util.js";
import { libauthOutputToCashScriptOutput } from "cashscript/dist/utils.js";
import { serializeOutput } from "../utils/crypto.js";


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
 * @param {Object} [opts.contractOpts]
 * @param {import("@generalprotocols/anyhedge").ContractDataV2} opts.contractData
 * @returns 
 */
export function calculateTotalFundingSatoshis(opts) {
  const treasuryContract = opts?.contractOpts
    ? new TreasuryContract(opts?.contractOpts)
    : undefined

  const contractData = parseContractData(opts?.contractData)

  const calculatedSettlementTxFee = getAnyhedgeSettlementTxFeeSize({ contractData })

  // this is how much sats needed in anyhedge contract's UTXO
  const totalFundingSats = contractData.metadata.shortInputInSatoshis +
                          contractData.metadata.longInputInSatoshis +
                          calculatedSettlementTxFee + 1332n;

  const decodedAddress = cashAddressToLockingBytecode(contractData.address)
  if (typeof decodedAddress === 'string') throw new Error(decodedAddress)
  const outputSize = BigInt(decodedAddress.bytecode.byteLength) + 9n;
  const tcInputSize = BigInt(getTreasuryContractInputSize({ contractData, treasuryContract }));

  let addtlFeeSats = 0n;
  const lpFee = getLiquidityFee(contractData);
  if (lpFee) {
    if (typeof lpFee === 'string') throw new Error(lpFee)
    addtlFeeSats += getFeeSats(lpFee)
  }

  const settlementServiceFee = getSettlementServiceFee(contractData);
  if (settlementServiceFee) {
    if (typeof settlementServiceFee === 'string') throw new Error(settlementServiceFee)
    addtlFeeSats += getFeeSats(settlementServiceFee);
  }

  const P2PKH_INPUT_SIZE = 148n; // in some libraries it's 141n but others is 148, just following anyhedge's constants.js
  const p2shMinerFeeSatoshis = outputSize + P2PKH_INPUT_SIZE + tcInputSize + 10n;
  const p2shTotalFundingSats = totalFundingSats + addtlFeeSats + p2shMinerFeeSatoshis;
  
  const p2pkhMinerFeeSatoshis = outputSize + (P2PKH_INPUT_SIZE * 2n) + 10n;
  const p2pkhTotalFundingSats = totalFundingSats + addtlFeeSats + p2pkhMinerFeeSatoshis;

  const longFundingSats = contractData.metadata.longInputInSatoshis;

  const manager = new AnyHedgeManager({ contractVersion: contractData.version })
  const anyhedgeTotalFundingSats = manager.calculateTotalRequiredFundingSatoshis(contractData)

  return {
    totalFundingSats: Number(totalFundingSats),

    shortFundingUtxoSats: Number(p2shTotalFundingSats - longFundingSats),
    longFundingSats: Number(longFundingSats),

    // data here just for reference
    metadata: {
      anyhedgeTotalFundingSats: Number(anyhedgeTotalFundingSats),
      calculatedSettlementTxFee: Number(calculatedSettlementTxFee),
      addtlFeeSats: Number(addtlFeeSats),

      p2shMinerFeeSatoshis: Number(p2shMinerFeeSatoshis),
      p2shTotalFundingSats: Number(p2shTotalFundingSats),
      p2pkhMinerFeeSatoshis: Number(p2pkhMinerFeeSatoshis),
      p2pkhTotalFundingSats: Number(p2pkhTotalFundingSats),
    },
  }
}

/**
 * @param {Object} opts
 * @param {import("@generalprotocols/anyhedge").ContractData} opts.contractData
 */
export function getContractDataOutputs(opts) {
  const contractData = parseContractData(opts?.contractData)
  const outputs = constructFundingOutputs(contractData)
    .map(libauthOutputToCashScriptOutput)
    .map(serializeOutput)

  return { success: true, outputs }
}
