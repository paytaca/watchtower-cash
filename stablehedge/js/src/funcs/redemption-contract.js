import { RedemptionContract } from '../contracts/redemption-contract/index.js'
import { parseUtxo } from '../utils/crypto.js'

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
 * @param {import('cashscript').Utxo} opts.reserveUtxo
 * @param {import('cashscript').Utxo} opts.depositUtxo
 * @param {String} opts.treasuryContractAddress
 * @param {String} opts.recipientAddress
 * @param {String} opts.priceMessage
 * @param {String} opts.priceMessageSig
 */
export async function deposit(opts) {
  const redemptionContract = new RedemptionContract(opts?.contractOpts)

  const reserveUtxo = parseUtxo(opts?.reserveUtxo)
  const depositUtxo = parseUtxo(opts?.depositUtxo)
  const transaction = await redemptionContract.deposit({
    reserveUtxo, depositUtxo,
    treasuryContractAddress: opts?.treasuryContractAddress,
    recipientAddress: opts?.recipientAddress,
    priceMessage: opts?.priceMessage,
    priceMessageSig: opts?.priceMessageSig,
  })

  if (typeof transaction === 'string') return { success: false, error: transaction }
  return { success: true, tx_hex: await transaction.build() }
}

/**
 * @param {Object} opts 
 * @param {Object} opts.contractOpts 
 * @param {import('cashscript').UtxoP2PKH} opts.authKeyUtxo 
 * @param {import('cashscript').UtxoP2PKH[]} opts.contractUtxos
 * @param {import('cashscript').UtxoP2PKH} opts.recipientAddress
 * @param {import('cashscript').UtxoP2PKH} opts.authKeyRecipient
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
  })

  if (typeof transaction === 'string') return { success: false, error: transaction }
  return { success: true, tx_hex: await transaction.build() }
}
