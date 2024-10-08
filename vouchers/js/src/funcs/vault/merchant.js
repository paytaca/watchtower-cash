import { MerchantVault } from '../../contract/merchant.js'
import { toBytes32 } from '../utils.js'


/**
 * 
 * @param {Object} opts
 * @param {Object} opts.params
 * @param {Object} opts.params.merchant
 * @param {String} opts.params.merchant.verificationCategory
 * @param {Object} opts.params.merchant.pubkey
 * @param {String} opts.params.merchant.pubkey.merchant = 0th index pubkey
 * @param {String} opts.params.merchant.pubkey.device = 1<PADDED_ZEROS><POSID>th index pubkey of POS device 
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
 const vault = new MerchantVault(opts)
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
 * 
 * @param {Object} opts.params
 * @param {String} opts.params.category
 * @param {Number} opts.params.latestBlockTimestamp
 * 
 * @param {Object} opts.params.merchant
 * @param {String} opts.params.merchant.verificationCategory
 * @param {Object} opts.params.merchant.pubkey
 * @param {String} opts.params.merchant.pubkey.merchant = 0th index pubkey
 * @param {String} opts.params.merchant.pubkey.device = 1<PADDED_ZEROS><POSID>th index pubkey of POS device 
 * 
 * @param {Object} opts.params.funder
 * @param {String} opts.params.funder.address
 * @param {String} opts.params.funder.wif
 * 
 * @param {Object} opts.options
 * @param {String} opts.options.network = 'mainnet | chipnet'
 * 
 * @returns {
 *    success: Boolean,
 *    txid: String
 * }
 * 
 */
export async function refund (opts) {
  const latestBlockTimestamp =  opts.params?.latestBlockTimestamp
  const category =  opts.params?.category
  const vault = new MerchantVault(opts)
  const transaction = await vault.refund(category, latestBlockTimestamp)
  return transaction
}


/**
 * @param {Object} opts
 * @param {Object} opts.params
 * @param {Object} opts.params.merchant
 * @param {String} opts.params.merchant.verificationCategory
 * @param {Object} opts.params.merchant.pubkey
 * @param {String} opts.params.merchant.pubkey.merchant = 0th index pubkey
 * @param {String} opts.params.merchant.pubkey.device = 1<PADDED_ZEROS><POSID>th index pubkey of POS device 
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
export async function claim (opts) {
  const category = opts.params?.merchant?.voucher?.category
  const vault = new MerchantVault(opts)
  const transaction = await vault.claim(category)
  return transaction
}


/**
 * @param {Object} opts
 * @param {Object} opts
 * @param {Object} opts.params
 * @param {Object} opts.params.merchant
 * @param {String} opts.params.merchant.verificationCategory
 * @param {Object} opts.params.merchant.pubkey
 * @param {String} opts.params.merchant.pubkey.merchant = 0th index pubkey
 * @param {String} opts.params.merchant.pubkey.device = 1<PADDED_ZEROS><POSID>th index pubkey of POS device 
 * @param {Object} opts.params.merchant.voucher
 * @param {String} opts.params.merchant.voucher.category
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
  
  const vault = new MerchantVault(opts)
  const transaction = await vault.emergencyRefund(sender, refundAmount)
  return transaction
}