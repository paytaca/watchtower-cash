import Vault from "./vault"


/**
 * @param {Object} [opts]
 * @param {Object} [opts.params]
 * @param {String} opts.params.userPubkey
 * @param {String} opts.params.merchantPubkey
 * 
 * @param {Object} [opts.options]
 * @param {String} opts.options.network 'chipnet | mainnet'
 * 
 */
export const getContract = (opts) => {
  const vault = new Vault(opts)
  return vault.contract
}