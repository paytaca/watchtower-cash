import { compileFile } from "cashc"
import { Contract, ElectrumNetworkProvider, isUtxoP2PKH, SignatureTemplate } from "cashscript"
import { hexToBin, base64ToBin } from "@bitauth/libauth"

import { P2PKH_INPUT_SIZE, VERSION_SIZE, LOCKTIME_SIZE } from 'cashscript/dist/constants.js'
import { calculateDust, getOutputSize } from "cashscript/dist/utils.js"

// import redemptionContractArtifact from './redemption-contract.json'
// import redemptionContractCode from './redemption-contract.cash'

import { toTokenAddress } from "../../utils/crypto.js"
import { decodePriceMessage, verifyPriceMessage } from "../../utils/price-oracle.js"
import { calculateInputSize } from "../../utils/transaction.js"

export class RedemptionContract {
  /**
   * @param {Object} opts
   * @param {Object} opts.params
   * @param {String} opts.params.authKeyId
   * @param {String} opts.params.tokenCategory
   * @param {String} opts.params.oraclePublicKey
   * @param {Object} opts.options
   * @param {'mainnet' | 'chipnet'} opts.options.network
   * @param {'p2sh20' | 'p2sh32'} opts.options.addressType
   */
  constructor(opts) {
    this.params = {
      authKeyId: opts?.params?.authKeyId,
      tokenCategory: opts?.params?.tokenCategory,
      oraclePublicKey: opts?.params?.oraclePublicKey,
    }

    this.options = {
      network: opts?.options?.network || 'mainnet',
      addressType: opts?.options?.addressType,
    }
  }

  get isChipnet() {
    return this.options?.network === 'chipnet'
  }

  getContract() {
    const provider = new ElectrumNetworkProvider(this.isChipnet ? 'chipnet' : 'mainnet')
    const opts = { provider, addressType: this.options?.addressType }
    const cashscriptFilename = 'redemption-contract.cash'
    const artifact = compileFile(new URL(cashscriptFilename, import.meta.url));
    // const artifact = redemptionContractArtifact
    const contractParams = [
      hexToBin(this.params.authKeyId).reverse(),
      hexToBin(this.params?.tokenCategory).reverse(),
      this.params?.oraclePublicKey,
    ]
    const contract = new Contract(artifact, contractParams, opts);

    if (contract.opcount > 201) console.warn(`Opcount must be at most 201. Got ${contract.opcount}`)
    if (contract.bytesize > 520) console.warn(`Bytesize must be at most 520. Got ${contract.bytesize}`)

    return contract
  }

  /**
   * @param {Object} opts
   * @param {import("cashscript").Utxo} opts.reserveUtxo
   * @param {import("cashscript").UtxoP2PKH} opts.depositUtxo
   * @param {String} [opts.treasuryContractAddress] if no address is provided, it is injecting liquidity
   * @param {String} opts.recipientAddress
   * @param {String} opts.priceMessage
   * @param {String} opts.priceMessageSig
   */
  async deposit(opts) {
    if (!opts?.depositUtxo) return 'Deposit UTXO not provided'
    if (opts?.depositUtxo?.token) return 'Deposit UTXO has a token'
    if (!opts?.reserveUtxo) return 'Reserve UTXO not provided'
    if (opts?.reserveUtxo?.token?.category !== this.params.tokenCategory) return 'Reserve UTXO provided does not contain fiat token'

    const priceMessageValid = verifyPriceMessage(
      opts?.priceMessage, opts?.priceMessageSig, this.params.oraclePublicKey, 
    )
    if (!priceMessageValid) return 'Invalid price message signature' 

    const priceData = decodePriceMessage(opts?.priceMessage)
    if (typeof priceData == 'string') return `Invalid price message: ${priceData}`

    const isInjectLiquidity = !opts?.treasuryContractAddress
    const reserveSupplyTokens = opts?.reserveUtxo?.token?.amount

    const HARDCODED_FEE = 1000n
    const releaseOutputSats = 1000n
    const totalDepositSats = opts?.depositUtxo?.satoshis - releaseOutputSats - HARDCODED_FEE
    const depositSats = isInjectLiquidity ? totalDepositSats : totalDepositSats / 2n;
    const releaseOutputTokens = BigInt(priceData.price) * totalDepositSats
    
    const remainingReserveSupplyTokens = reserveSupplyTokens - releaseOutputTokens
    if (remainingReserveSupplyTokens < 0n) return 'Insufficient reserve tokens'

    const depositUtxoTemplate = opts?.depositUtxo?.template ??
      new SignatureTemplate(opts?.depositUtxo?.wif)

    const recipientAddress = toTokenAddress(opts?.recipientAddress)

    const contract = this.getContract()
    const transaction = contract.functions.deposit(hexToBin(opts?.priceMessage), base64ToBin(opts?.priceMessageSig), isInjectLiquidity)
      .from(opts?.reserveUtxo)
      .fromP2PKH(opts?.depositUtxo, depositUtxoTemplate)
      .to(contract.tokenAddress, opts?.reserveUtxo.satoshis + depositSats, {
        category: opts?.reserveUtxo?.token?.category,
        amount: remainingReserveSupplyTokens,
        nft: opts?.reserveUtxo?.token?.nft,
      })
      .to(recipientAddress, releaseOutputSats, {
        category: this.params.tokenCategory,
        amount: releaseOutputTokens,
      })

    if (!isInjectLiquidity) {
      transaction.to(opts?.treasuryContractAddress, depositSats)
    }

    transaction.withHardcodedFee(HARDCODED_FEE)
    return transaction
  }

  /**
   * @param {Object} opts
   * @param {import("cashscript").Utxo} opts.reserveUtxo
   * @param {import("cashscript").UtxoP2PKH} opts.redeemUtxo
   * @param {String} opts.recipientAddress
   * @param {String} opts.priceMessage
   * @param {String} opts.priceMessageSig
   */
  async redeem(opts) {
    if (!opts?.redeemUtxo) return 'Redeem UTXO not provided'
    if (opts?.redeemUtxo?.token?.category !== this.params.tokenCategory) return 'Redeem UTXO is not fiat token'
    if (!opts?.reserveUtxo) return 'Reserve UTXO not provided'
    if (opts?.reserveUtxo?.token?.category !== this.params.tokenCategory) return 'Reserve UTXO provided does not contain fiat token'

    const priceMessageValid = verifyPriceMessage(
      opts?.priceMessage, opts?.priceMessageSig, this.params.oraclePublicKey, 
    )
    if (!priceMessageValid) return 'Invalid price message signature' 

    const priceData = decodePriceMessage(opts?.priceMessage)
    if (typeof priceData == 'string') return `Invalid price message: ${priceData}`

    const EXPECTED_TX_FEE = 1000n
    const tokenAmount = opts?.redeemUtxo?.token?.amount
    const redeemSats = tokenAmount / BigInt(priceData?.price)

    if (redeemSats < 546n) return 'Redeem amount too small'

    const contract = this.getContract()
    const feeToCover = opts?.redeemUtxo?.satoshis - EXPECTED_TX_FEE
    const remainingReserveSats = opts?.reserveUtxo.satoshis - redeemSats - feeToCover

    if (remainingReserveSats < 1000n) return 'Insufficient BCH balance'

    const redeemUtxoTemplate = opts?.redeemUtxo?.template ??
      new SignatureTemplate(opts?.redeemUtxo?.wif)

    const transaction = contract.functions.redeem(hexToBin(opts?.priceMessage), base64ToBin(opts?.priceMessageSig))
      .from(opts?.reserveUtxo)
      .fromP2PKH(opts?.redeemUtxo, redeemUtxoTemplate)
      .to(contract.tokenAddress, remainingReserveSats, {
        category: opts?.reserveUtxo?.token?.category,
        amount: opts?.reserveUtxo?.token?.amount + tokenAmount,
        nft: opts?.reserveUtxo?.token?.nft,
      })
      .to(opts?.recipientAddress, redeemSats)
      .withHardcodedFee(EXPECTED_TX_FEE)

    return transaction
  }

  /**
   * @param {Object} opts
   * @param {Boolean} opts.keepGuarded
   * @param {import("cashscript").Utxo[]} opts.inputs
   * @param {import("cashscript").Recipient[]} opts.outputs
   */
  async unlockWithNft(opts) {
    const authKeyUtxo = opts?.inputs?.[1]
    if (!authKeyUtxo) return 'Authkey not provided'
    if (authKeyUtxo?.token?.category !== this.params.authKeyId) return 'Invalid authkey id'
    if (authKeyUtxo?.token?.nft?.capability !== 'none') return 'Invalid authkey capability'
    if (authKeyUtxo?.token?.amount) return 'Authkey must not have token amount'

    const contract = this.getContract()
    const transaction = contract.functions.unlockWithNft(opts?.keepGuarded)
    opts?.inputs?.forEach(input => {
      input?.wif
        ? transaction.fromP2PKH(input, new SignatureTemplate(input.wif))
        : transaction.from(input)
    })

    transaction.to(opts?.outputs)
    return transaction
  }

  /**
   * @param {Object} opts
   * @param {String} opts.recipientAddress
   * @param {String} opts.authKeyRecipient
   * @param {import("cashscript").Utxo} opts.authKeyUtxo
   * @param {import("cashscript").Utxo[]} opts.contractUtxos
   */
  async sweep(opts) {
    const recipientAddress = opts?.recipientAddress
    const recipientTokenAddress = toTokenAddress(recipientAddress)
    const authKeyRecipient = opts?.authKeyRecipient
      ? toTokenAddress(opts?.authKeyRecipient)
      : recipientTokenAddress

    const contract = this.getContract()
    const utxos = opts?.contractUtxos?.length
      ? opts?.contractUtxos
      : await contract.getUtxos()
    if (utxos?.length <= 0) return 'No UTXO'

    /** @type {import("cashscript").Recipient[]} */
    const outputs = []
    const inputs = [...utxos]

    const assets = {
      totalSats: 0n,
      fiatTokens: [].map(() => ({
        category: '', amount: 0n,
      })),
      nfts: [].map(() => ({
        category: '', capability: '', commitment: '',
      }))
    }

    inputs.forEach(utxo => {
      assets.totalSats += utxo.satoshis
      if (!utxo.token) return
      const token = utxo.token

      if (token.amount) {
        const tokenBalance = assets.fiatTokens.find(tokenBal => tokenBal.category === token.category)
        if (tokenBalance) tokenBalance.amount += token.amount
        else assets.fiatTokens.push({ category: token.category, amount: token.amount })
      }

      if (token.nft) {
        assets.nfts.push({
          category: token.category,
          capability: token.nft.capability,
          commitment: token.nft.commitment,
        })
      }
    })

    assets.fiatTokens.forEach(tokenBalance => {
      outputs.push({
        to: recipientTokenAddress,
        amount: 1000n,
        token: {
          category: tokenBalance.category,
          amount: tokenBalance.amount,
        }
      })
    })

    assets.nfts.forEach(nft => {
      outputs.push({
        to: recipientTokenAddress,
        amount: 1000n,
        token: {
          category: nft.category,
          amount: 0n,
          nft: { capability: nft.capability, commitment: nft.commitment },
        }
      })
    })

    const authKeyUtxo = opts?.authKeyUtxo
    const authKeyOutput = {
      to: authKeyRecipient,
      amount: authKeyUtxo.satoshis,
      token: authKeyUtxo.token,
    }

    const inputSize = calculateInputSize(contract.functions.unlockWithNft(true))
    const feePerByte = 1.0

    const contractInputFeeSats = BigInt(Math.ceil((inputs.length * inputSize) * feePerByte))
    const authKeyInputFeeSats = BigInt(Math.ceil(P2PKH_INPUT_SIZE * feePerByte))
    const totalInputFeeSats = contractInputFeeSats + authKeyInputFeeSats
    const cashtokenOutputSats =  outputs
    .reduce((subtotal, output) => {
      return subtotal + output.amount
    }, 0n)

    const cashTokenOutputFees = outputs
      .reduce((subtotal, output) => {
        const outputFee = BigInt(Math.ceil(getOutputSize(output) * feePerByte))
        return subtotal + outputFee
      }, 0n)
    const authKeyOutputFee = BigInt(Math.ceil(getOutputSize(authKeyOutput) * feePerByte))
    const totalOutputAndFeesWithoutChange = cashtokenOutputSats + cashTokenOutputFees + authKeyOutputFee

    const baseFeeSats = BigInt(Math.ceil((VERSION_SIZE + LOCKTIME_SIZE) * feePerByte)) + 10n // added 10 sats for room for error
    const remainingSats = assets.totalSats - (baseFeeSats + totalInputFeeSats + totalOutputAndFeesWithoutChange)
    const changeOutput = {
      to: recipientAddress,
      amount: remainingSats,
    }
    const changeOutputFee = BigInt(Math.ceil(getOutputSize(changeOutput) * feePerByte))
    changeOutput.amount -= changeOutputFee
    if (changeOutput.amount > calculateDust(changeOutput)) {
      outputs.push(changeOutput)
    }

    // force authkey input to be index 1 follow smart contract conditions
    // force authkey output to be the same index to allow SINGLE|ANYONECANPAY sighash
    inputs.splice(1, 0, authKeyUtxo)
    outputs.splice(1, 0, authKeyOutput)

    const transaction = await this.unlockWithNft({ keepGuarded: false, inputs: inputs, outputs: outputs })
    if (typeof transaction === 'string') return transaction

    transaction.withFeePerByte(feePerByte)
    return transaction  
  }
}
