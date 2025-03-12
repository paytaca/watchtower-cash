import { binToHex } from "@bitauth/libauth";
import { generateRedeemScript, scriptToBytecode} from "@cashscript/utils"
import { encodeConstructorArguments } from "cashscript/dist/Argument.js";
import { getArtifact, getBaseBytecode, parseContractData } from "../utils/anyhedge.js";

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
  const encodedArgs = encodeConstructorArguments(artifact, parameters).slice().reverse();
  const argsScript = generateRedeemScript(new Uint8Array(), encodedArgs);
  const bytecodesHex = argsScript.map(script => {
    return binToHex(scriptToBytecode([script]))
  })

  // const argsCount = bytecodesHex.length
  const segment1 = bytecodesHex.slice(-3).join('');
  const segment2 = bytecodesHex.slice(-8, -4).join('');

  return {
    segment1,
    segment2,
    payoutSats: bytecodesHex[4],
    lowPrice: bytecodesHex[3],
    highPrice: bytecodesHex[2],
    startTs: bytecodesHex[1],
    maturityTs: bytecodesHex[0],
  }
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
