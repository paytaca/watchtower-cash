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
export const getContract = async (opts) => {
  const vault = new Vault(opts)
  const balance = await vault.contract.getBalance()
  return {
    contract: vault.contract,
    balance: Number(balance) / 1e8
  }
}