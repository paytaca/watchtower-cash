import { Vault } from '../contract/vault.js'


export function compileVaultContract (opts) {
  const vault = new Vault(opts)
  const contract = vault.getContract()

  return {
    address: contract.address,
    tokenAddress: contract.tokenAddress
  }
}
