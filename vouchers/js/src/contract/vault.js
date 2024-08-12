import { compileFile } from "cashc";
import { reverseHex } from "../funcs/utils.js"
import {
  Contract,
  ElectrumNetworkProvider,
} from "cashscript";


/**
 * @param {Object} opts
 * @param {Object} opts.params
 * @param {Object} opts.params.merchant
 * @param {String} opts.params.merchant.address
 * @param {String} opts.params.merchant.pubkey
 * @param {Object} opts.options
 * @param {String} opts.options.network = 'mainnet | chipnet' 
 * 
 */
export class Vault {

  constructor (opts) {
    this.merchant = opts?.params?.merchant
    this.network = opts?.options?.network
    this.dust = 1000n
  }

  get contractCreationParams () {
    return [
      this.merchant?.pubkey,
    ]
  }

  get provider () {
    return new ElectrumNetworkProvider(this.network)
  }

  get artifact () {
    return compileFile(new URL('vault.cash', import.meta.url))
  }

  get contract () {
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

  getContract () {
    return this.contract
  }

  async claim (category) {
    let voucherUtxos = []
    
    while (voucherUtxos.length !== 2) {
      const utxos = await this.provider.getUtxos(this.contract.address)
      voucherUtxos = utxos.filter(utxo => utxo?.token?.category === category)
    }

    if (voucherUtxos.length === 0) throw new Error(`No category ${category} utxos found`)

    const lockNftUtxo = voucherUtxos.find(utxo => utxo.satoshis !== this.dust)
    const transaction = await this.contract.functions.claim(reverseHex(category))
      .from(voucherUtxos)
      .to(this.contract.address, lockNftUtxo.satoshis)
      .withoutTokenChange()
      .withoutChange()
      .send()

    const result = {
      success: true,
      txid: transaction.txid
    }
    return result
  }

  async release () {
    const balance = await this.contract.getBalance()
    const amount = balance - this.dust
    const transaction = await this.contract.functions
      .release()
      .to(this.merchant?.address, amount)
      .withHardcodedFee(this.dust)
      .send()

    const result = {
      success: true,
      txid: transaction.txid
    }
    return result
  }

  async refund (category, latestBlockTimestamp) {
    const utxos = await this.provider.getUtxos(this.contract.address)
    const lockNftUtxo = utxos.find(utxo =>
      utxo?.token?.category === category &&
      utxo?.satoshis !== this.dust
    )

    if (!lockNftUtxo) throw new Error(`No lock NFT of category ${category} utxos found`)

    // get latest MTP (median timestamp) from latest block
    const refundedAmount = lockNftUtxo.satoshis - this.dust
    const transaction = await this.contract.functions
      .refund()
      .from(lockNftUtxo)
      .to(this.merchant?.address, refundedAmount)
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