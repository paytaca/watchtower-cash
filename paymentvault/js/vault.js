import { compileFile } from 'cashc'
import {
  Contract,
  ElectrumNetworkProvider,
} from "cashscript"


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
export default class Vault {

  constructor (opts) {
    this.params = opts?.params
    this.network = opts?.options?.network
  }

  get contractParams () {
    return [
      this.params?.userPubkey,
      this.params?.merchantPubkey
    ]
  }

  get provider () {
    return new ElectrumNetworkProvider(this.network)
  }

  get artifact () {
    return compileFile(new URL('vault.cash', import.meta.url));
  }

  get contract () {
    const contract = new Contract(
      this.artifact,
      this.contractParams,
      { provider: this.provider }
    )

    if (contract.bytesize > 520) throw new Error('Contract max bytesize should be 520 bytes')
    if (contract.opcount > 201) throw new Error('Contract max opcount should be 201 bytes')

    return contract
  }

}