import BCHJS from "@psf/bch-js"
import { compileFile } from "cashc";
import { reverseHex, toBytes32 } from "../funcs/utils.js"
import {
  Contract,
  ElectrumNetworkProvider,
  SignatureTemplate,
} from "cashscript";


const bchjs = new BCHJS()


/**
 * @param {Object} opts
 * @param {Object} opts.params
 * @param {Object} opts.params.merchant
 * @param {String} opts.params.merchant.address = 1<PADDED_ZEROS><POSID>th address of POS Device
 * @param {String} opts.params.merchant.pubkey
 * @param {String} opts.params.merchant.vaultTokenAddress
 * @param {String} opts.params.merchant.scriptHash = 32 byte script pubkey of merchant vault
 * @param {String} opts.params.merchant.verificationCategory
 * 
 * @param {Object} opts.params.funder
 * @param {String} opts.params.funder.address
 * @param {String} opts.params.funder.wif
 * 
 * @param {Object} opts.options
 * @param {String} opts.options.network = 'mainnet | chipnet' 
 * 
 */
export class PosDeviceVault {

  constructor (opts) {
    this.merchant = opts?.params?.merchant
    this.funder = opts?.params?.funder
    this.network = opts?.options?.network
    this.dust = 1000n
    this.mintFee = 2000n
    this.neededFromFunder = this.dust + this.mintFee
  }

  get contractCreationParams () {
    return [
      this.merchant?.pubkey,
      this.merchant?.scriptHash,
      reverseHex(this.merchant?.verificationCategory) 
    ]
  }

  get provider () {
    return new ElectrumNetworkProvider(this.network)
  }

  get artifact () {
    return compileFile(new URL('device_vault.cash', import.meta.url))
  }

  get contract () {
    const contract = new Contract(
      this.artifact,
      this.contractCreationParams,
      { provider: this.provider }
    )
    
    if (contract.opcount > 201) throw new Error(`Opcount max size is 201 bytes. Got ${opcount}`)
    if (contract.bytesize > 520) throw new Error(`Bytesize max is 520 bytes. Got ${bytesize}`)

    return contract
  }

  get scriptHashCommitment () {
    return toBytes32(this.contract.bytecode, 'hex', true)
  }

  get funderSignature () {
    const keyPair = bchjs.ECPair.fromWIF(this.funder?.wif)
    return new SignatureTemplate(keyPair)
  }

  getContract () {
    return this.contract
  }

  async sendTokens (voucherCategory) {
    const utxos = await this.contract.getUtxos()
    const funderUtxos = await this.provider.getUtxos(this.funder?.address)

    const funderUtxo = funderUtxos.find(utxo => !utxo?.token && utxo.satoshis >= this.neededFromFunder)
    const keyNftUtxo = utxos.find(utxo => utxo?.token?.category === voucherCategory)
    const mintingNftUtxo = utxos.find(
      utxo => {
        return (
          utxo?.token?.nft?.capability === 'minting' &&
          utxo?.token?.category === this.merchant?.verificationCategory
        )
      }
    )
    const contractUtxos = [ mintingNftUtxo, keyNftUtxo ]

    if (funderUtxo === undefined) throw new Error('No more available UTXOs on funder')

    funderUtxo.wif = this.funder?.wif
    const verificationToken = {
      amount: 0n,
      category: this.merchant?.verificationCategory,
      nft: {
        capability: 'none',
        commitment: this.scriptHashCommitment
      }
    }

    const funderChange = funderUtxo.satoshis - this.neededFromFunder

    let transaction = this.contract.functions
      .sendTokens(reverseHex(voucherCategory))
      .from(contractUtxos)
      .fromP2PKH(funderUtxo, this.funderSignature)
      .to(this.contract.tokenAddress, this.dust, mintingNftUtxo?.token)
      .to(this.merchant?.vaultTokenAddress, this.dust, verificationToken)
      .to(this.merchant?.vaultTokenAddress, this.dust, keyNftUtxo?.token)
    
    if (funderChange >= this.dust) transaction = transaction.to(this.funder?.address, funderChange)

    transaction = await transaction.withHardcodedFee(this.mintFee).send()

    return {
      success: true,
      txid: transaction.txid
    }
  }

  async release (amount) {
    const utxos = await this.contract.getUtxos()
    const contractBchUtxos = utxos.filter(utxo => !utxo?.token)

    let bchBalance = 0n
    for (const utxo of contractBchUtxos) {
      bchBalance += utxo.satoshis
    }

    const possibleFee = bchBalance - amount
    let fee = possibleFee
    
    let transaction = this.contract.functions
      .release()
      .from(contractBchUtxos)
      .to(this.merchant?.address, amount)

    if (possibleFee < this.dust) {
      fee = this.dust

      const funderUtxos = await this.provider.getUtxos(this.funder?.address)
      const funderUtxo = funderUtxos.find(utxo => !utxo?.token && utxo.satoshis >= this.dust)
      transaction = transaction.fromP2PKH(funderUtxo, this.funderSignature)

      const funderChange = funderUtxo.satoshis - fee
      if (funderChange >= this.dust) transaction = transaction.to(this.funder?.address, funderChange)
    }
  
    transaction = await transaction.withHardcodedFee(fee).send()

    return {
      success: true,
      txid: transaction.txid
    }
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