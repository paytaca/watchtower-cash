import { Vault } from '../contract/vault.js'


/**
 * 
 * @param {Object} opts
 * 
 * @param {Object} opts.params
 * @param {String} opts.params.merchantReceiverPk
 * @param {String} opts.params.merchantSignerPk
 * 
 * @param {Object} opts.options
 * @param {String} opts.options.network = 'mainnet | chipnet'
 * 
 * @returns {address: String, tokenAddress: String}
 * 
 */
export function compileVaultContract (opts) {
  const vault = new Vault(opts)
  const contract = vault.getContract()

  return {
    address: contract.address,
    tokenAddress: contract.tokenAddress
  }
}
