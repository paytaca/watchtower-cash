import { cashAddressToLockingBytecode, hexToBin, isHex } from "@bitauth/libauth";
import { contractDataToParameters, getArtifact, getBaseBytecode, getContractParamBytecodes } from "./anyhedge.js";

import { calculateInputSize } from "./transaction.js";
import { createProxyFunder, createTreasuryContract } from "./factory.js";
import { baseBytecodeToHex, encodeParameterBytecode } from "./contracts.js";
import { TreasuryContract } from "../contracts/treasury-contract/index.js";


const LP_FEE_NAME = 'Liquidity Premium'
const SETTLEMENT_SERVICE_FEE_NAME = 'Settlement Service Fee'

/**
 * @param {Object} opts
 * @param {TreasuryContract} opts.treasuryContract
 * @param {import("@generalprotocols/anyhedge").ContractDataV2} opts.contractData
 * @param {String} opts.anyhedgeVersion
 */
export function getTreasuryContractInputSize(opts) {
  const treasuryContract = opts?.treasuryContract || createTreasuryContract({...opts, version: 'v3' })?.manager
  const contract = treasuryContract.getContract();
  const contractData = opts?.contractData
  const params = prepareParamForTreasuryContract(
    contractData, { treasuryContractVersion: treasuryContract.options.version },
  )
  const treasuryContractInputSize = calculateInputSize(contract.functions.spendToAnyhedge(
    ...params,
  )) - 1; // there is a +1n in the script for margin but we dont want this for this case
  return treasuryContractInputSize
}

/**
 * @param {Object} opts 
 * @param {import("@generalprotocols/anyhedge").ContractData} opts.contractData 
 */
export function getAnyhedgeContractInputSize(opts) {
  const contractData = opts?.contractData;
  const { artifact } = getArtifact()
  const parameters = contractDataToParameters(contractData)
  const paramBytecodes = encodeParameterBytecode(artifact, parameters)
  const { bytecode } = getBaseBytecode(contractData)

  const _payoutParamLength = (64n + 16n + 2n) * 2n; // includes price settlement msg & sig & previous msg & sig
  const _selectorSize = 4n; // not sure but this might just be an integer of 4 bytes
  const _paramBytecodesSize = BigInt(paramBytecodes.reverse().join('').length / 2);
  const _baseBytecodeSize = BigInt(bytecode.length / 2);

  // This is the unlocking script contents:
  // <func_params_bytecodes><selector><contract_param_bytecodes><base_bytecode>
  const settlementUnlockingScriptLength = _payoutParamLength + _selectorSize +
    _paramBytecodesSize + _baseBytecodeSize;

  // Addtl 43 bytes are for the following
  // 32B txid | 4B index | 4B sequence | 3B script length
  // NOTE: on p2pkh script length is just 1B since it's less than 253 but
  // anyhedge is most likey over 253, so we use 3B since its between 254 and 65536
  return settlementUnlockingScriptLength + 43n;
}


/**
 * @param {Object} opts 
 * @param {import("@generalprotocols/anyhedge").ContractData} opts.contractData 
 * @param {Boolean} opts.verify 
 */
export function getAnyhedgeSettlementTxFeeSize(opts) {
  const contractData = opts?.contractData;

  const settlementInputSize = getAnyhedgeContractInputSize({ contractData });
  const shortLockscriptSize = BigInt(contractData.parameters.shortLockScript.length / 2);
  const longLockscriptSize = BigInt(contractData.parameters.longLockScript.length / 2);

  // + 9n for each for other output data: 8b amount | 1b lockscript length
  // + 10n is for base tx fee: 4b version | 4b locktime | 1b input count | 1b output count
  const settlementTxFee = shortLockscriptSize + 9n +
                          longLockscriptSize + 9n +
                          settlementInputSize +
                          10n;

  if (opts?.verify && settlementTxFee !== contractData.metadata.minerCostInSatoshis) {
    throw new Error(`Inaccurate settlement transaction fee calculation. Got ${settlementTxFee}, expected ${contractData.metadata.minerCostInSatoshis}`)
  }

  return settlementTxFee
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
 * 
 * @param {import("@generalprotocols/anyhedge").ContractFee} fee 
 */
export function getFeeSats(fee) {
  const decodedAddress = cashAddressToLockingBytecode(fee.address)
  if (typeof decodedAddress === 'string') return decodedAddress

  const lockscriptSize = BigInt(decodedAddress.bytecode.byteLength)
  return fee.satoshis + lockscriptSize + 9n;
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

  if (feeSats < MIN_FEE || feeSats > MAX_FEE) return `Invalid fee amount ${feeSats}`

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

  if (feeSats < MIN_FEE || feeSats > MAX_FEE) return `Invalid fee amount: ${feeSats}`

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
      hexToBin(shortMutualRedeemPublicKey),
      hexToBin(bytecodesHex.slice(1, 3).reverse().join('')),
      hexToBin(longLockScript),
      param5,
      hexToBin(satsForNominalUnitsAtHighLiquidation),
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