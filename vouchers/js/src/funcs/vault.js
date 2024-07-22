import { Vault } from '../contract/vault.js'


/**
 * 
 * @param {Object} opts
 * 
 * @param {Object} opts.params
 * @param {Object} opts.params.merchant
 * @param {String} opts.params.merchant.receiverPk
 * 
 * @param {Object} opts.options
 * @param {String} opts.options.network = 'mainnet | chipnet'
 * 
 * @returns {address: String, tokenAddress: String}
 * 
 */
export async function compileVaultContract (opts) {
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
 * @param {String} opts.params.merchant.receiverPk
 * @param {Object} opts.params.sender
 * @param {String} opts.params.sender.pubkey
 * @param {String} opts.params.sender.address
 * @param {Number} opts.params.refundAmount
 * 
 * @param {Object} opts.options
 * @param {String} opts.options.network = 'mainnet | chipnet'
 * 
 * @returns {transaction: Object}
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

      break
    } catch (err) {
      // added catch here to see which utxo matches the sender
      console.log(err)
    }
  }

  return transaction
}


/**
 * 
 * @param {String} category
 * 
 * @param {Object} merchant
 * @param {String} merchant.address
 * @param {String} merchant.pubkey
 * 
 * @param {String} network 'mainnet | chipnet'
 * 
 * @returns {transaction: Object}
 * 
 */
export async function claimVoucher ({ category, merchant, network }) {
  const vaultParams = {
    params: {
      merchantReceiverPk: merchant?.pubkey,
    },
    options: {
      network
    }
  }
  const claimPayload = {
    voucherClaimerAddress: merchant?.address,
    category,
  }

  try {
    const vault = new Vault(vaultParams)
    const transaction = await vault.claim(claimPayload)
    return transaction
  } catch (err) {}

  return { success: false }
}


/**
 * 
 * @param {String} category
 * 
 * @param {Object} merchant
 * @param {String} merchant.address
 * @param {String} merchant.pubkey
 * 
 * @param {String} network 'mainnet | chipnet'
 * 
 * @param {Number} latestBlockTimestamp
 * 
 * @returns {transaction: Object}
 * 
 */
export async function refundVoucher ({ category, merchant, network, latestBlockTimestamp }) {
  const vaultParams = {
    params: {
      merchantReceiverPk: merchant?.pubkey,
    },
    options: {
      network
    }
  }
  const refundPayload = {
    voucherClaimerAddress: merchant?.address,
    latestBlockTimestamp,
    category,
  }

  try {
    const vault = new Vault(vaultParams)
    const transaction = await vault.refund(refundPayload)
    return transaction
  } catch (err) {}

  return { success: false }
}