import { compileFile } from "cashc"
import { Contract, ElectrumNetworkProvider, isUtxoP2PKH, SignatureTemplate, TransactionBuilder } from "cashscript"
import { cashAddressToLockingBytecode, hexToBin } from "@bitauth/libauth"
import { scriptToBytecode } from "@cashscript/utils"

import { P2PKH_INPUT_SIZE, VERSION_SIZE, LOCKTIME_SIZE } from 'cashscript/dist/constants.js'
import { calculateDust, getOutputSize } from "cashscript/dist/utils.js"

import redemptionContractArtifact from './redemption-contract.json' assert { type: 'json'}
import redemptionContractV2Artifact from './redemption-contract-v2.json' assert { type: 'json'}

import { toTokenAddress } from "../../utils/crypto.js"
import { decodePriceMessage, verifyPriceMessage } from "../../utils/price-oracle.js"
import { calculateInputSize, satoshisToToken, tokenToSatoshis } from "../../utils/transaction.js"
import { addPrecision, removePrecision } from "../../utils/transaction.js"
import { numbersToCumulativeHexString } from "../../utils/math.js"

export class RedemptionContract {
  /**
   * @param {Object} opts
   * @param {Object} opts.params
   * @param {String} opts.params.authKeyId
   * @param {String} opts.params.tokenCategory
   * @param {String} opts.params.oraclePublicKey
   * @param {String} opts.params.treasuryContractAddress
   * @param {Object} opts.options
   * @param {'v1' | 'v2' | 'v3'} opts.options.version
   * @param {'mainnet' | 'chipnet'} opts.options.network
   * @param {'p2sh20' | 'p2sh32'} opts.options.addressType
   */
  constructor(opts) {
    this.params = {
      authKeyId: opts?.params?.authKeyId,
      tokenCategory: opts?.params?.tokenCategory,
      oraclePublicKey: opts?.params?.oraclePublicKey,
      treasuryContractAddress: opts?.params?.treasuryContractAddress,
    }

    this.options = {
      network: opts?.options?.network || 'mainnet',
      addressType: opts?.options?.addressType,
      version: opts?.options?.version,
    }
  }

  get isChipnet() {
    return this.options?.network === 'chipnet'
  }

  static getArtifact(version) {
    let artifactOrFileName = redemptionContractArtifact;
    if (version === 'v2') {
      artifactOrFileName = redemptionContractV2Artifact;
    } else if (version !== 'v1') {
      artifactOrFileName = `redemption-contract-${version}.cash`;
    }

    if (typeof artifactOrFileName !== 'string') return artifactOrFileName
    const artifact = compileFile(new URL(artifactOrFileName, import.meta.url));
    return artifact;
  }

  get contractParameters() {
    const contractParams = [
      hexToBin(this.params?.authKeyId).reverse(),
      hexToBin(this.params?.tokenCategory).reverse(),
      hexToBin(this.params?.oraclePublicKey),
    ]

    if (this.options.version !== 'v1') {
      const lockingBytecode = cashAddressToLockingBytecode(this.params.treasuryContractAddress)
      contractParams.push(lockingBytecode.bytecode);
    }

    return contractParams
  }

  getContract() {
    const provider = new ElectrumNetworkProvider(this.isChipnet ? 'chipnet' : 'mainnet')
    const opts = { provider, addressType: this.options?.addressType }
    const artifact = RedemptionContract.getArtifact(this.options.version);
    const contract = new Contract(artifact, this.contractParameters, opts);

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
   * @param {Number} [opts.fee]
   * @param {String} opts.priceMessage
   * @param {String} opts.priceMessageSig
   * @param {Number} [opts.locktime]
   */
  async deposit(opts) {
    if (!opts?.depositUtxo) return 'Deposit UTXO not provided'
    if (opts?.depositUtxo?.token) return 'Deposit UTXO has a token'
    if (!opts?.reserveUtxo) return 'Reserve UTXO not provided'
    if (opts?.reserveUtxo?.token?.category !== this.params.tokenCategory) return 'Reserve UTXO provided does not contain fiat token'
    if (opts?.fee && (!opts?.treasuryContractAddress || this.options.version !== 'v3')) {
      return 'Provided fee on invalid transaction type or contract version'
    }

    const priceMessageValid = verifyPriceMessage(
      opts?.priceMessage, opts?.priceMessageSig, this.params.oraclePublicKey, 
    )
    if (!priceMessageValid) return 'Invalid price message signature' 

    const priceData = decodePriceMessage(opts?.priceMessage)
    if (typeof priceData == 'string') return `Invalid price message: ${priceData}`

    const isInjectLiquidity = !opts?.treasuryContractAddress
    const reserveSupplyTokens = opts?.reserveUtxo?.token?.amount
    const fee = opts?.fee ? BigInt(opts?.fee) : 0n;

    const HARDCODED_FEE = 1000n
    const releaseOutputSats = 1000n
    const totalDepositSats = opts?.depositUtxo?.satoshis - releaseOutputSats - HARDCODED_FEE - fee;
    const depositSats = isInjectLiquidity ? totalDepositSats : totalDepositSats / 2n;
    const releaseOutputTokens = satoshisToToken(totalDepositSats, priceData.price)
    
    const remainingReserveSupplyTokens = reserveSupplyTokens - releaseOutputTokens
    if (remainingReserveSupplyTokens < 0n) return 'Insufficient reserve tokens'

    const depositUtxoTemplate = opts?.depositUtxo?.template ??
      new SignatureTemplate(opts?.depositUtxo?.wif)

    const recipientAddress = toTokenAddress(opts?.recipientAddress)

    const contract = this.getContract()
    const functionArgs = [
      hexToBin(opts?.priceMessage),
      hexToBin(opts?.priceMessageSig),
      isInjectLiquidity,
    ]
    if (this.options.version === 'v3') functionArgs.push(fee)

    const transaction = contract.functions.deposit(...functionArgs)
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
      transaction.to(opts?.treasuryContractAddress, depositSats + fee)
    }

    transaction.withHardcodedFee(HARDCODED_FEE)
    if (!Number.isNaN(opts?.locktime)) {
      transaction.withTime(opts?.locktime)
    }
    return transaction
  }

  /**
   * @param {Object} opts
   * @param {import("cashscript").Utxo} opts.reserveUtxo
   * @param {import("cashscript").UtxoP2PKH} opts.redeemUtxo
   * @param {String} opts.recipientAddress
   * @param {Number} [opts.fee]
   * @param {String} opts.priceMessage
   * @param {String} opts.priceMessageSig
   * @param {Number} [opts.locktime]
   */
  async redeem(opts) {
    if (!opts?.redeemUtxo) return 'Redeem UTXO not provided'
    if (opts?.redeemUtxo?.token?.category !== this.params.tokenCategory) return 'Redeem UTXO is not fiat token'
    if (!opts?.reserveUtxo) return 'Reserve UTXO not provided'
    if (opts?.reserveUtxo?.token?.category !== this.params.tokenCategory) return 'Reserve UTXO provided does not contain fiat token'
    if (opts?.fee && this.options.version !== 'v3') {
      return 'Provided fee on invalid transaction type or contract version'
    }

    const priceMessageValid = verifyPriceMessage(
      opts?.priceMessage, opts?.priceMessageSig, this.params.oraclePublicKey, 
    )
    if (!priceMessageValid) return 'Invalid price message signature' 

    const priceData = decodePriceMessage(opts?.priceMessage)
    if (typeof priceData == 'string') return `Invalid price message: ${priceData}`

    const EXPECTED_TX_FEE = 1000n
    const fee = opts?.fee ? BigInt(opts?.fee) : 0n;
    const tokenAmount = opts?.redeemUtxo?.token?.amount
    const redeemSats = tokenToSatoshis(tokenAmount, priceData.price) - fee;

    if (redeemSats < 546n) return 'Redeem amount too small'

    const contract = this.getContract()
    const feeToCover = opts?.redeemUtxo?.satoshis - EXPECTED_TX_FEE
    const remainingReserveSats = opts?.reserveUtxo.satoshis - redeemSats - feeToCover

    if (remainingReserveSats < 1000n) return 'Insufficient BCH balance'

    const redeemUtxoTemplate = opts?.redeemUtxo?.template ??
      new SignatureTemplate(opts?.redeemUtxo?.wif)

    const functionArgs = [hexToBin(opts?.priceMessage), hexToBin(opts?.priceMessageSig)];
    if (this.options.version === 'v3') functionArgs.push(fee);
    const transaction = contract.functions.redeem(...functionArgs)
      .from(opts?.reserveUtxo)
      .fromP2PKH(opts?.redeemUtxo, redeemUtxoTemplate)
      .to(contract.tokenAddress, remainingReserveSats, {
        category: opts?.reserveUtxo?.token?.category,
        amount: opts?.reserveUtxo?.token?.amount + tokenAmount,
        nft: opts?.reserveUtxo?.token?.nft,
      })
      .to(opts?.recipientAddress, redeemSats)
      .withHardcodedFee(EXPECTED_TX_FEE)

    if (!Number.isNaN(opts?.locktime)) {
      transaction.withTime(opts?.locktime)
    }

    return transaction
  }

  /**
   * @param {Object} opts
   * @param {Boolean} opts.keepGuarded
   * @param {import("cashscript").Utxo[]} opts.inputs
   * @param {import("cashscript").Recipient[]} opts.outputs
   * @param {Number} [opts.locktime]
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
    if (!Number.isNaN(opts?.locktime)) {
      transaction.withTime(opts?.locktime)
    }
    return transaction
  }

  /**
   * @param {Object} opts
   * @param {String} opts.recipientAddress
   * @param {String} opts.authKeyRecipient
   * @param {import("cashscript").Utxo} opts.authKeyUtxo
   * @param {import("cashscript").Utxo[]} opts.contractUtxos
   * @param {Number} [opts.locktime]
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

    const transaction = await this.unlockWithNft({
      keepGuarded: false,
      inputs: inputs,
      outputs: outputs,
      locktime: opts?.locktime,
    })
    if (typeof transaction === 'string') return transaction

    transaction.withFeePerByte(feePerByte)
    return transaction  
  }

  /**
   * - Unlike sweep, each tokens & bch are consolidated into one output
   *   this will just pass the utxos as is without consolidating
   * - Would require funding utxos to keep utxo values as is,
   *   if there is none it will use one the utxos' BCH (will keep dust in mind)
   * - In case there are changes to the contract's code and need to transfer assets
   *   to the new contract's version
   * 
   * @typedef {import("cashscript").UtxoP2PKH} UtxoP2PKH
   * @typedef {import("cashscript").Utxo} Utxo
   * 
   * @param {Object} opts 
   * @param {Number} [opts.locktime]
   * @param {String} opts.recipientAddress
   * @param {UtxoP2PKH} opts.authKeyUtxo
   * @param {(Utxo | UtxoP2PKH)[]} opts.utxos
   * @param {UtxoP2PKH[]} opts.fundingUtxos
   */
  async transferUtxos(opts) {
    const recipientAddress = opts?.recipientAddress
    const recipientTokenAddress = toTokenAddress(recipientAddress)

    const contract = this.getContract()
    const utxos = opts?.utxos?.length ? opts?.utxos : await contract.getUtxos()

    const inputs = [...utxos]

    /** @type {import("cashscript").Output[]} */
    const outputs = inputs.map(input => {
      return {
        to: input?.token ? recipientTokenAddress : recipientAddress,
        amount: input.satoshis,
        token: input?.token,
      }
    })

    // force authkey input to be index 1 follow smart contract conditions
    // force authkey output to be the same index to allow SINGLE|ANYONECANPAY sighash
    const authKeyUtxo = opts?.authKeyUtxo
    const authKeyOutput = {
      to: authKeyUtxo.template.unlockP2PKH().generateLockingBytecode(),
      amount: authKeyUtxo.satoshis,
      token: authKeyUtxo.token,
    }
    inputs.splice(1, 0, authKeyUtxo)
    outputs.splice(1, 0, authKeyOutput)

    // to limit confusion, underscore prefix has added precision
    const feePerByte = 1.0
    const _feePerByte = addPrecision(feePerByte)
    const __baseFee = addPrecision(VERSION_SIZE + LOCKTIME_SIZE + 2) * _feePerByte
    const _baseFee = removePrecision(__baseFee)

    const contractInputSize = calculateInputSize(contract.functions.unlockWithNft(true))
    const _totalInputFeeSats = inputs.reduce((_subtotal, input) => {
      const inputSize = isUtxoP2PKH(input) ? P2PKH_INPUT_SIZE : contractInputSize
      const __inputFeeSats = addPrecision(inputSize) * _feePerByte
      return removePrecision(__inputFeeSats) + _subtotal
    }, 0n)

    const _totalOutputFeeSats = outputs.reduce((_subtotal, output) => {
      const __outputFee = addPrecision(getOutputSize(output)) * _feePerByte
      return _subtotal + removePrecision(__outputFee)
    }, 0n)

    let _totalInputSats = addPrecision(inputs.reduce((subtotal, input) => subtotal + input.satoshis, 0n))
    let _totalOutputSats = addPrecision(outputs.reduce((subtotal, output) => subtotal + output.amount, 0n))
    let _totalFeeSats = _baseFee + _totalInputFeeSats + _totalOutputFeeSats

    // add funding utxos
    for (let index=0; index < opts?.fundingUtxos?.length || 0; index++) {
      const fundingUtxo = opts?.fundingUtxos[index];
      if (_totalInputSats >= _totalOutputSats + _totalFeeSats) break

      const inputSize = isUtxoP2PKH(fundingUtxo) ? P2PKH_INPUT_SIZE : contractInputSize
      const __inputFeeSats = addPrecision(inputSize) * _feePerByte
      _totalFeeSats += removePrecision(__inputFeeSats)
      _totalInputSats += addPrecision(fundingUtxo.satoshis)
      inputs.push(fundingUtxo)

      /** @type {import("cashscript").Output} */
      const fundingUtxoOutput = {
        to: fundingUtxo?.template?.unlockP2PKH()?.generateLockingBytecode()?.length
          ? fundingUtxo?.template?.unlockP2PKH()?.generateLockingBytecode()
          : contract.address,
        amount: fundingUtxo.satoshis,
        token: fundingUtxo?.token,
      }
      const outputSize = getOutputSize(fundingUtxoOutput)
      const __outputFeeSats = addPrecision(outputSize) * _feePerByte
      const _outputFeeSats = removePrecision(__outputFeeSats)
      const _dust = addPrecision(calculateDust(fundingUtxoOutput))

      const _remainingSats = _totalInputSats - (_totalOutputSats + _totalFeeSats + _outputFeeSats)
      if (_remainingSats >= _dust) {
        fundingUtxoOutput.amount = removePrecision(_remainingSats)
        _totalOutputSats += _remainingSats
        _totalFeeSats += _outputFeeSats
        outputs.push(fundingUtxoOutput)
      }
    }

    // use sats from utxos as fee if funding utxos is not enough
    for (let index=0; index < outputs.length; index++) {
      const output = outputs[index];
      if (output.token && output.amount <= 1000n) continue;

      const _deficitSats = (_totalOutputSats + _totalFeeSats) - _totalInputSats
      const deficitSats = removePrecision(_deficitSats) + 1n
      if (deficitSats < 0) break

      const dust = output.token ? 1000n : 546n;
      if (output.amount <= dust) continue;

      const diff = output.amount - dust
      const deducted = deficitSats < diff  ? deficitSats : diff
      output.amount -= deducted
      _totalOutputSats -= addPrecision(deducted)
    }

    const transaction = await this.unlockWithNft({
      inputs, outputs,
      locktime: opts?.locktime,
      keepGuarded: false,
    })

    if (typeof transaction === 'string') return transaction

    transaction.withFeePerByte(feePerByte)
    return transaction
  }

  /**
   * @param {Object} opts 
   * @param {Number} [opts.locktime]
   * @param {import("cashscript").UtxoP2PKH} opts.feeFunderUtxo
   * @param {import("cashscript").Output} [opts.feeFunderOutput]
   * @param {import("cashscript").Utxo[]} opts.inputs
   * @param {Number} [opts.satoshis] falsey value would mean to consolidate all inputs into 1 utxo
   */
  async consolidate(opts) {
    const contract = this.getContract()
    if (!contract.functions.consolidate) return 'Contract function not supported'

    const cashtokenInputs = opts?.inputs?.filter(input => input?.token?.category === this.params.tokenCategory)
    if (cashtokenInputs?.length > 1) return 'Multiple cashtoken inputs not supported'
    const cashtokenInputIndex = opts?.inputs?.findIndex(input => input?.token?.category === this.params.tokenCategory)
    if (cashtokenInputIndex > 0) return 'Cashtoken input must be at index 1'

    const feeFunderUtxo = opts?.feeFunderUtxo
    const feeFunderOutput = opts?.feeFunderOutput
    const totalSats = opts.inputs.reduce((subtotal, utxo) => subtotal + utxo.satoshis, 0n)
    const opData = numbersToCumulativeHexString([0n, ...opts?.inputs?.map(input => input.satoshis)])
    const opDataBytecode = scriptToBytecode([0x6a, hexToBin(opData)])

    const builder = new TransactionBuilder({ provider: contract.provider })
      .addInput(feeFunderUtxo, feeFunderUtxo.template.unlockP2PKH())
      .addInputs(opts.inputs, contract.unlock.consolidate())

    if (feeFunderOutput) {
      builder.addOutput(feeFunderOutput)
    } else {
      builder.addOutput({
        to: feeFunderUtxo.template.unlockP2PKH().generateLockingBytecode(),
        amount: feeFunderUtxo.satoshis
      })
    }

    builder.addOutput({ to: opDataBytecode, amount: 0n })

    const tokenData = cashtokenInputs?.[0]?.token
    const recipient = tokenData ? contract.tokenAddress : contract.address
    if (opts.satoshis) {
      builder.addOutput({ to: recipient, amount: BigInt(opts.satoshis), token: tokenData })
      builder.addOutput({ to: contract.address, amount: totalSats - BigInt(opts.satoshis) })
    } else {
      builder.addOutput({ to: recipient, amount: totalSats, token: tokenData })
    }

    if (Number.isSafeInteger(opts?.locktime)) {
      builder.setLocktime(opts?.locktime)
    }

    if (!feeFunderOutput) {
      const txSize = builder.build().length
      builder.outputs[0].amount -= BigInt(txSize / 2)
    }

    return builder
  }
}
