import { Vault } from '../contract/vault.js'


/**
 * 
 * @param {Object} opts
 * 
 * @param {Object} opts.params
 * @param {Object} opts.params.merchant
 * @param {String} opts.params.merchant.address
 * @param {String} opts.params.merchant.pubkey
 * 
 * @param {Object} opts.options
 * @param {String} opts.options.network = 'mainnet | chipnet'
 * 
 * @returns {
 *    address: String,
 *    tokenAddress: String,
 *    balance: Number
 * }
 * 
 */
export async function compile (opts) {
  const vault = new Vault(opts)
  const contract = vault.getContract()
  const balance = await contract.getBalance()

  return {
    address: contract.address,
    tokenAddress: contract.tokenAddress,
    balance: Number(balance)
  }
}


/**
 * 
 * @param {Object} opts
 * 
 * @param {Object} opts.params
 * @param {Object} opts.params.merchant
 * @param {String} opts.params.merchant.address
 * @param {String} opts.params.merchant.pubkey
 * @param {Object} opts.params.sender
 * @param {String} opts.params.sender.pubkey
 * @param {String} opts.params.sender.address
 * @param {Number} opts.params.refundAmount
 * 
 * @param {Object} opts.options
 * @param {String} opts.options.network = 'mainnet | chipnet'
 * 
 * @returns {
 *    transaction: Object,
 *    success: Boolean
 * }
 * 
 */
export async function emergencyRefund (opts) {
  const vault = new Vault(opts)
  const contract = vault.getContract()
  const { provider } = vault.getProviderAndArtifact()

  const senderPubkey = opts?.params?.sender?.pubkey
  const senderAddress = opts?.params?.sender?.address
  const refundAmount = BigInt(opts?.params?.refundAmount)

  let transaction = {}
  let utxos = await provider.getUtxos(contract.address)
  utxos = utxos.filter(utxo => !utxo?.token && utxo?.satoshis === refundAmount)
  
  for (const utxo of utxos) {
    try {
      const fee = 1000n
      const dust = 546n
      const finalAmount = utxo?.satoshis - fee

      if (finalAmount < dust) continue

      transaction = contract.functions
        .emergencyRefund(senderPubkey)
        .from([ utxo ])
        .to(senderAddress, finalAmount)
        .withoutChange()
        .send()

      transaction.success = true
      return transaction
    } catch (err) {
      // added catch here to see which utxo matches the sender
      console.log(err)
    }
  }

  return { success: false }
}


/**
 * @param {Object} opts
 * @param {Object} opts.params
 * @param {String} opts.params.category
 * @param {Object} opts.params.merchant
 * @param {String} opts.params.merchant.address
 * @param {String} opts.params.merchant.pubkey
 * @param {Object} opts.options
 * @param {String} opts.options.network = 'mainnet | chipnet' 
 * 
 * @returns {
 *    success: Boolean,
 *    txid: String
 * }
 * 
 */
export async function claim (opts) {
  const category = opts.params?.category
  delete opts.params?.category

  try {
    const vault = new Vault(opts)
    const transaction = await vault.claim(category)
    return transaction
  } catch (err) {}

  return { success: false }
}


/**
 * @param {Object} opts
 * @param {Object} opts.params
 * @param {Object} opts.params.merchant
 * @param {String} opts.params.merchant.address
 * @param {String} opts.params.merchant.pubkey
 * @param {Object} opts.options
 * @param {String} opts.options.network = 'mainnet | chipnet' 
 * 
 * @returns {
*    success: Boolean,
*    txid: String
* }
* 
*/
export async function release (opts) {
  try {
    const vault = new Vault(opts)
    const transaction = await vault.release()
    return transaction
  } catch (err) {}

  return { success: false }
}


/**
 * 
 * @param {Object} opts
 * 
 * @param {Object} opts.params
 * @param {String} opts.params.category
 * @param {Number} opts.params.latestBlockTimestamp
 * @param {Object} opts.params.merchant
 * @param {String} opts.params.merchant.address
 * @param {String} opts.params.merchant.pubkey
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

  delete opts.params?.category
  delete opts.params?.latestBlockTimestamp

  try {
    const vault = new Vault(opts)
    const transaction = await vault.refund(category, latestBlockTimestamp)
    return transaction
  } catch (err) {}

  return { success: false }
}