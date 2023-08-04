import { compileFile } from "cashc";
import {
  Contract,
  ElectrumNetworkProvider,
} from "cashscript";


export class Vault {

  constructor (opts) {
    this.merchantPkHash = opts?.params?.merchantPkHash
    this.network = opts?.options?.network
  }

  get contractCreationParams () {
    return [
      this.merchantPkHash
    ]
  }

  getContract () {
    const provider = new ElectrumNetworkProvider(this.network)
    const artifact = compileFile(new URL('vault.cash', import.meta.url))
    const contract = new Contract(
      artifact,
      this.contractCreationParams,
      { provider }
    )

    const bytesize = contract.bytesize
    const opcount = contract.opcount
    
    if (opcount > 201) throw new Error(`Opcount max size is 201 bytes. Got ${opcount}`)
    if (bytesize > 520) throw new Error(`Bytesize max is 520 bytes. Got ${bytesize}`)

    return contract
  }

}
