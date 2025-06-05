import { RedemptionContract } from '../contracts/redemption-contract/index.js'
import { baseBytecodeToHex } from '../utils/contracts.js';
import { parseCashscriptOutput, parseUtxo } from '../utils/crypto.js'


export function getRedemptionContractArtifact() {
  const artifact = RedemptionContract.getArtifact();
  return { success: true, artifact }
}

/**
 * @param {Object} opts
 * @param {Object} [opts.version=v2]
 */
export function getRedemptionContractBaseBytecode(opts) {
  const version = opts?.version || 'v2'
  const artifact = RedemptionContract.getArtifact()
  return {
    version: version,
    bytecode: baseBytecodeToHex(artifact.bytecode)
  }
}

/**
 * @param {Object} opts 
 */
export function compileRedemptionContract(opts) {
  const redemptionContract = new RedemptionContract(opts)
  const contract = redemptionContract.getContract()
  return {
    address: contract.address,
    tokenAddress: contract.tokenAddress,
    params: redemptionContract.params,
    options: redemptionContract.options,
    bytecode: contract.bytecode,
  }
}

/**
 * @param {Object} opts 
 * @param {Object} opts.contractOpts 
 * @param {import('cashscript').UtxoP2PKH} opts.authKeyUtxo 
 * @param {import('cashscript').UtxoP2PKH[]} opts.contractUtxos
 * @param {import('cashscript').UtxoP2PKH} opts.recipientAddress
 * @param {import('cashscript').UtxoP2PKH} opts.authKeyRecipient
 * @param {Number} [opts.locktime]
 */
export async function sweepRedemptionContract(opts) {
  const redemptionContract = new RedemptionContract(opts?.contractOpts)
  const authKeyUtxo = parseUtxo(opts?.authKeyUtxo)
  let contractUtxos = undefined
  if (opts?.contractUtxos?.length) contractUtxos = opts.contractUtxos.map(parseUtxo)
  const transaction = await redemptionContract.sweep({
    contractUtxos,
    authKeyUtxo, 
    recipientAddress: opts?.recipientAddress,
    authKeyRecipient: opts?.authKeyRecipient,
    locktime: opts?.locktime,
  })
  if (typeof transaction === 'string') return { success: false, error: transaction }
  return { success: true, tx_hex: await transaction.build() }
}

/**
 * @param {Object} opts 
 * @param {Object} opts.contractOpts 
 * @param {import('cashscript').UtxoP2PKH} opts.authKeyUtxo 
 * @param {import('cashscript').Utxo[]} opts.utxos
 * @param {String} opts.recipientAddress
 * @param {Number} [opts.locktime]
 */
export async function transferRedemptionContractAssets(opts) {
  const redemptionContract = new RedemptionContract(opts?.contractOpts)
  const authKeyUtxo = parseUtxo(opts?.authKeyUtxo)
  let utxos = undefined
  if (opts?.utxos?.length) utxos = opts.utxos.map(parseUtxo)
  const transaction = await redemptionContract.transferUtxos({
    utxos,
    authKeyUtxo, 
    recipientAddress: opts?.recipientAddress,
    locktime: opts?.locktime,
  })
  if (typeof transaction === 'string') return { success: false, error: transaction }
  return { success: true, tx_hex: await transaction.build() }
}

/**
 * @param {Object} opts 
 * @param {Object} opts.contractOpts 
 * @param {import('cashscript').Utxo} opts.reserveUtxo 
 * @param {import('cashscript').UtxoP2PKH} opts.depositUtxo
 * @param {String} [opts.treasuryContractAddress]
 * @param {String} opts.priceMessage
 * @param {String} opts.priceMessageSig
 * @param {Number} [opts.locktime]
 */
export async function deposit(opts) {
  const redemptionContract = new RedemptionContract(opts?.contractOpts)
  const reserveUtxo = parseUtxo(opts?.reserveUtxo)
  const depositUtxo = parseUtxo(opts?.depositUtxo)
  const transaction = await redemptionContract.deposit({
    reserveUtxo,
    depositUtxo,
    recipientAddress: opts?.recipientAddress,
    treasuryContractAddress: opts?.treasuryContractAddress,
    priceMessage: opts?.priceMessage,
    priceMessageSig: opts?.priceMessageSig,
    locktime: opts?.locktime,
  })

  if (typeof transaction === 'string') return { success: false, error: transaction }
  return { success: true, tx_hex: await transaction.build() }
}


/**
 * @param {Object} opts 
 * @param {Object} opts.contractOpts 
 * @param {import('cashscript').Utxo} opts.reserveUtxo 
 * @param {import('cashscript').UtxoP2PKH} opts.redeemUtxo
 * @param {String} opts.recipientAddress
 * @param {String} opts.priceMessage
 * @param {String} opts.priceMessageSig
 * @param {Number} [opts.locktime]
 */
export async function redeem(opts) {
  const redemptionContract = new RedemptionContract(opts?.contractOpts)
  const reserveUtxo = parseUtxo(opts?.reserveUtxo)
  const redeemUtxo = parseUtxo(opts?.redeemUtxo)
  const transaction = await redemptionContract.redeem({
    reserveUtxo,
    redeemUtxo,
    recipientAddress: opts?.recipientAddress,
    priceMessage: opts?.priceMessage,
    priceMessageSig: opts?.priceMessageSig,
    locktime: opts?.locktime,
  })

  if (typeof transaction === 'string') return { success: false, error: transaction }
  return { success: true, tx_hex: await transaction.build() }
}


/**
 * @param {Object} opts
 * @param {Object} opts.contractOpts
 * @param {Boolean} [opts.keepGuarded]
 * @param {import('cashscript').Utxo[]} opts.inputs
 * @param {import('cashscript').Output} opts.outputs
 * @param {Number} [opts.locktime]
 */
export async function unlockRedemptionContractWithNft(opts) {
  const redemptionContract = new RedemptionContract(opts?.contractOpts)

  const inputs = opts?.inputs?.map(parseUtxo)
  const outputs = opts?.outputs?.map(parseCashscriptOutput)

  const transaction = await redemptionContract.unlockWithNft({
    keepGuarded: opts?.keepGuarded,
    inputs, outputs,
    locktime: opts?.locktime,
  })

  if (typeof transaction === 'string') return { success: false, error: transaction }
  return { success: true, tx_hex: await transaction.build() }
}


/**
 * @param {Object} opts
 * @param {Object} opts.contractOpts
 * @param {Number} [opts.locktime]
 * @param {import("cashscript").UtxoP2PKH} opts.feeFunderUtxo
 * @param {import("cashscript").Output} [opts.feeFunderOutput]
 * @param {import("cashscript").Utxo[]} opts.inputs
 * @param {Number} opts.satoshis
 */
export async function consolidateRedemptionContract(opts) {
  const redemptionContract = new RedemptionContract(opts?.contractOpts)

  const feeFunderUtxo = parseUtxo(opts?.feeFunderUtxo)
  if (!feeFunderUtxo.template) return { success: false, error: 'Invalid fee funder' }

  const feeFunderOutput = opts?.feeFunderOutput
    ? parseCashscriptOutput(opts?.feeFunderOutput)
    : undefined

  const inputs = opts?.inputs?.map(parseUtxo)

  const transaction = await redemptionContract.consolidate({
    feeFunderUtxo,
    feeFunderOutput,
    inputs,
    satoshis: opts?.satoshis,
    locktime: opts?.locktime,
  })

  if (typeof transaction === 'string') return { success: false, error: transaction }
  return { success: true, tx_hex: await transaction.build() }
}
