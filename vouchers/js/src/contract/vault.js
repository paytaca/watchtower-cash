import { compileFile } from "cashc";
import { reverseHex } from "../funcs/utils.js"
import {
  Contract,
  ElectrumNetworkProvider,
} from "cashscript";


export class Vault {

  constructor (opts) {
    this.merchant = opts?.params?.merchant
    this.network = opts?.options?.network
  }

  get contractCreationParams () {
    return [
      this.merchant?.receiverPk,
    ]
  }

  get provider () {
    return new ElectrumNetworkProvider(this.network)
  }

  get artifact () {
    return compileFile(new URL('vault.cash', import.meta.url))
  }

  getContract () {
    const contract = new Contract(
      this.artifact,
      this.contractCreationParams,
      { provider: this.provider }
    )

    const bytesize = contract.bytesize
    const opcount = contract.opcount
    
    if (opcount > 201) throw new Error(`Opcount max size is 201 bytes. Got ${opcount}`)
    if (bytesize > 520) throw new Error(`Bytesize max is 520 bytes. Got ${bytesize}`)

    return contract
  }

  async claim ({ category, voucherClaimerAddress }) {
    const contract = this.getContract()
    let voucherUtxos = []
    
    while (voucherUtxos.length !== 2) {
      const utxos = await this.provider.getUtxos(contract.address)
      voucherUtxos = utxos.filter(utxo => utxo?.token?.category === category)
    }

    if (voucherUtxos.length === 0) throw new Error(`No category ${category} utxos found`)

    const lockNftUtxo = voucherUtxos.find(utxo => utxo.satoshis !== this.dust)
    const transaction = await contract.functions.claim(reverseHex(category))
      .from(voucherUtxos)
      .to(voucherClaimerAddress, lockNftUtxo.satoshis)
      .withoutTokenChange()
      .withoutChange()
      .send()

    const result = {
      success: true,
      txid: transaction.txid
    }
    return result
  }

  async refund ({ category, voucherClaimerAddress, latestBlockTimestamp }) {
    const contract = this.getContract()
    const utxos = await this.provider.getUtxos(contract.address)
    const lockNftUtxo = utxos.find(utxo =>
      utxo?.token?.category === category &&
      utxo?.satoshis !== this.dust
    )

    if (!lockNftUtxo) throw new Error(`No lock NFT of category ${category} utxos found`)

    // get latest MTP (median timestamp) from latest block
    const refundedAmount = lockNftUtxo.satoshis - this.dust
    const transaction = await contract.functions
      .refund()
      .from(lockNftUtxo)
      .to(voucherClaimerAddress, refundedAmount)
      .withoutTokenChange()
      .withHardcodedFee(this.dust)
      .withTime(latestBlockTimestamp)
      .send()

    const result = {
      success: true,
      txid: transaction.txid
    }
    return result
  }
  
}