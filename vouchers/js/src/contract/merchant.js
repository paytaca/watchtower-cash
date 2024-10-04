import { compileFile } from "cashc";
import { reverseHex, toBytes32 } from "../funcs/utils.js"
import {
  Contract,
  ElectrumNetworkProvider,
} from "cashscript";


/**
 * @param {Object} opts
 * @param {Object} opts.params
 * @param {Object} opts.params.merchant
 * @param {String} opts.params.merchant.verificationCategory
 * @param {Object} opts.params.merchant.pubkey
 * @param {String} opts.params.merchant.pubkey.merchant = 0th index pubkey
 * @param {String} opts.params.merchant.pubkey.device = 1<PADDED_ZEROS><POSID>th index pubkey of POS device 
 * 
 * @param {Object} opts.options
 * @param {String} opts.options.network = 'mainnet | chipnet' 
 * 
 */
export class MerchantVault {

  constructor (opts) {    
    this.merchant = opts?.params?.merchant
    this.network = opts?.options?.network
    this.dust = 1000n
  }

  get contractCreationParams () {
    return [
      this.merchant?.pubkey?.merchant,
      reverseHex(this.merchant?.verificationCategory),
    ]
  }

  get provider () {
    return new ElectrumNetworkProvider(this.network)
  }

  get artifacts () {
    return {
      merchant: compileFile(new URL('merchant_vault.cash', import.meta.url)),
      device: compileFile(new URL('device_vault.cash', import.meta.url)),
    }
  }

  get contract () {
    const merchantContract = new Contract(
      this.artifacts.merchant,
      this.contractCreationParams,
      { provider: this.provider }
    )
    
    if (merchantContract.opcount > 201) throw new Error(`Opcount max size is 201 bytes. Got ${opcount}`)
    if (merchantContract.bytesize > 520) throw new Error(`Bytesize max is 520 bytes. Got ${bytesize}`)
    
    return merchantContract
  }

  get deviceContract () {
    const merchantContractScriptHash = toBytes32(this.contract.bytecode, 'hex')
    const deviceContractParams = [
      this.merchant?.pubkey?.device,
      merchantContractScriptHash,
      reverseHex(this.merchant?.verificationCategory)
    ]

    const deviceContract = new Contract(
      this.artifacts.device,
      deviceContractParams,
      { provider: this.provider }
    )
    
    if (deviceContract.opcount > 201) throw new Error(`Opcount max size is 201 bytes. Got ${opcount}`)
    if (deviceContract.bytesize > 520) throw new Error(`Bytesize max is 520 bytes. Got ${bytesize}`)

    return deviceContract
  }

  async getBalance () {
    const utxos = await this.contract.getUtxos()
    const bchUtxos = utxos.filter(utxo => !utxo?.token)
    
    const balance = await this.contract.getBalance()
    const bchBalance = bchUtxos.reduce((acc, obj) => acc + obj?.satoshis, 0n)
    const tokenBalance = balance - bchBalance

    return {
      bch: Number(bchBalance) / 1e8,
      tokens: Number(tokenBalance) / 1e8,
    }
  }

  async claim (voucherCategory) {
    let _utxos = await this.contract.getUtxos()
    let voucherUtxos = _utxos.filter(utxo => utxo?.token?.category === voucherCategory)

    if (voucherUtxos.length < 2) throw new Error('Key and Lock NFTs should both be present before claiming')
    if (voucherUtxos.length === 0) throw new Error(`No category ${voucherCategory} utxos found`)
    
    // Do not burn verification token to be used as fee for POS device release to merchant
    const verificationTokenUtxo = _utxos.find(utxo => utxo?.token?.category === this.merchant?.verificationCategory)
    const lockNftUtxo = voucherUtxos.find(utxo => {
      return (
        utxo?.token?.category !== this.merchant?.verificationCategory && 
        utxo.satoshis !== this.dust
      )
    })
    voucherUtxos.push(verificationTokenUtxo)
    
    const transaction = await this.contract.functions
      .claim(reverseHex(voucherCategory))
      .from(voucherUtxos)
      .to(this.deviceContract.address, lockNftUtxo.satoshis)
      .to(this.deviceContract.tokenAddress, this.dust, verificationTokenUtxo?.token)
      .withHardcodedFee(1500n)
      .withoutTokenChange()
      .withoutChange()
      .send()

    return {
      success: true,
      txid: transaction.txid
    }
  }

  async refund (category, latestBlockTimestamp) {
    const utxos = await this.contract.getUtxos()
    const lockNftUtxo = utxos.find(utxo =>
      utxo?.token?.category === category &&
      utxo?.satoshis !== this.dust
    )

    if (!lockNftUtxo) throw new Error(`No lock NFT of category ${category} utxos found`)

    const excessForFee = lockNftUtxo.satoshis - this.dust
    if (excessForFee < this.dust) return

    const transaction = await this.contract.functions
      .refund()
      .from([ lockNftUtxo ])
      .to(this.merchant?.address, excessForFee)
      .withHardcodedFee(this.dust)
      .withTime(latestBlockTimestamp)
      .withoutTokenChange()
      .send()

    const result = {
      success: true,
      txid: transaction.txid
    }
    return result
  }

  async emergencyRefund (sender, amount) {
    const senderPubkey = sender?.pubkey
    const senderAddress = sender?.address
    const refundAmount = BigInt(amount)

    let transaction = {}
    let utxos = await this.contract.getUtxos()
    utxos = utxos.filter(utxo => !utxo?.token && utxo?.satoshis === refundAmount)
    
    for (const utxo of utxos) {
      try {
        const fee = 1000n
        const dust = 546n
        const finalAmount = utxo?.satoshis - fee

        if (finalAmount < dust) continue

        transaction = await this.contract.functions
          .emergencyRefund(senderPubkey)
          .from([ utxo ])
          .to(senderAddress, finalAmount)
          .withoutChange()
          .send()

        return {
          txid: transaction.txid,
          success: true
        }
      } catch (err) {
        // added catch here to see which utxo matches the sender
        console.log(err)
      }
    }

    throw new Error('No UTXO found')
  }
  
}