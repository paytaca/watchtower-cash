import { PosDeviceVault } from '../../contract/device.js'
import { toBytes32 } from '../utils.js'


/**
 * 
 * @param {Object} opts
 * @param {Object} opts.params
 * @param {Object} opts.params.merchant
 * @param {String} opts.params.merchant.address = 1<PADDED_ZEROS><POSID>th address of POS Device
 * @param {String} opts.params.merchant.pubkey
 * @param {String} opts.params.merchant.vaultTokenAddress
 * @param {String} opts.params.merchant.scriptHash = 32 byte script pubkey of merchant vault
 * @param {String} opts.params.merchant.verificationCategory
 * 
 * @param {Object} opts.params.funder
 * @param {String} opts.params.funder.address
 * @param {String} opts.params.funder.wif
 * 
 * @param {Object} opts.options
 * @param {String} opts.options.network = 'mainnet | chipnet'
 * 
 * @returns {
 *    address: String,
 *    tokenAddress: String,
 *    scriptHash: String,
 *    balance: Number (BCH)
 * }
 * 
 */
export async function compile (opts) {
  const vault = new PosDeviceVault(opts)
  const balance = await vault.getBalance()

  return {
    address: vault.contract.address,
    tokenAddress: vault.contract.tokenAddress,
    scriptHash: toBytes32(vault.contract.bytecode, 'hex', true),
    balance,
  }
}


/**
 * @param {Object} opts
 * @param {Object} opts.params
 * @param {Object} opts.params.merchant
 * @param {String} opts.params.merchant.address = 1<PADDED_ZEROS><POSID>th address of POS Device
 * @param {String} opts.params.merchant.pubkey
 * @param {String} opts.params.merchant.vaultTokenAddress
 * @param {String} opts.params.merchant.scriptHash = 32 byte script pubkey of merchant vault
 * @param {String} opts.params.merchant.verificationCategory
 * 
 * @param {Object} opts.params.funder
 * @param {String} opts.params.funder.address
 * @param {String} opts.params.funder.wif
 * 
 * @param {Object} opts.params.sender
 * @param {String} opts.params.sender.pubkey
 * @param {String} opts.params.sender.address
 * @param {Number} opts.params.refundAmount
 * 
 * @param {Object} opts.options
 * @param {String} opts.options.network = 'mainnet | chipnet'
 * 
 * @returns {
 *    txid: String,
 *    success: Boolean
 * }
 * 
 */
export async function emergencyRefund (opts) {
  const sender = opts?.params?.sender
  const refundAmount = opts?.params?.refundAmount

  const vault = new PosDeviceVault(opts)
  const transaction = await vault.emergencyRefund(sender, refundAmount)
  return transaction
}


/**
 * @param {Object} opts
 * @param {Object} opts.params
 * @param {Object} opts.params.merchant
 * @param {String} opts.params.merchant.address = 1<PADDED_ZEROS><POSID>th address of POS Device
 * @param {String} opts.params.merchant.pubkey
 * @param {String} opts.params.merchant.vaultTokenAddress
 * @param {String} opts.params.merchant.scriptHash = 32 byte script pubkey of merchant vault
 * @param {String} opts.params.merchant.verificationCategory
 * 
 * @param {Object} opts.params.funder
 * @param {String} opts.params.funder.address
 * @param {String} opts.params.funder.wif
 * 
 * @param {Object} opts.options
 * @param {String} opts.options.network = 'mainnet | chipnet' 
 * 
 *
 * @returns {
 *    success: Boolean,
 *    txid: String
 * }
 * 
 */
export async function release (opts) {
  const vault = new PosDeviceVault(opts)
  const transaction = await vault.release()
  return transaction
}


/**
 * @param {Object} opts
 * @param {Object} opts.params
 * @param {Object} opts.params.merchant
 * @param {String} opts.params.merchant.address = 1<PADDED_ZEROS><POSID>th address of POS Device
 * @param {String} opts.params.merchant.pubkey
 * @param {String} opts.params.merchant.vaultTokenAddress
 * @param {String} opts.params.merchant.scriptHash = 32 byte script pubkey of merchant vault
 * @param {String} opts.params.merchant.verificationCategory
 * @param {Object} opts.params.merchant.voucher
 * @param {String} opts.params.merchant.voucher.category
 * 
 * @param {Object} opts.params.funder
 * @param {String} opts.params.funder.address
 * @param {String} opts.params.funder.wif
 * 
 * @param {Object} opts.options
 * @param {String} opts.options.network = 'mainnet | chipnet' 
 * 
 *
 * @returns {
*    success: Boolean,
*    txid: String
* }
* 
*/
export async function sendTokens (opts) {
  const category = opts?.params?.merchant?.voucher?.category
  const vault = new PosDeviceVault(opts)
  const transaction = await vault.sendTokens(category)
  return transaction
}