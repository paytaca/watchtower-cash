import { getBaseBytecode, getContractParamBytecodes, parseContractData } from "../utils/anyhedge.js";

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
