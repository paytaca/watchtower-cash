import { compileFile } from "cashc"
import { Contract, ElectrumNetworkProvider, HashType, SignatureAlgorithm, SignatureTemplate, TransactionBuilder } from "cashscript"
import { binToHex, hexToBin, secp256k1 } from "@bitauth/libauth"

import { calculateDust, createSighashPreimage, getOutputSize } from "cashscript/dist/utils.js"
import { LOCKTIME_SIZE, P2PKH_INPUT_SIZE, VERSION_SIZE } from "cashscript/dist/constants.js"
import { hash256, scriptToBytecode } from "@cashscript/utils"

import { toTokenAddress } from "../../utils/crypto.js"
import { calculateInputSize, cashscriptTxToLibauth } from "../../utils/transaction.js"
import { numbersToCumulativeHexString } from "../../utils/math.js"
import { prepareParamForTreasuryContract } from "../../utils/anyhedge-funding.js"

export class TreasuryContract {
  /**
   * @param {Object} opts
   * @param {Object} opts.params
   * @param {String} opts.params.authKeyId
   * @param {String[]} opts.params.pubkeys
   * @param {String} opts.params.anyhedgeBaseBytecode
   * @param {String} opts.params.redemptionTokenCategory
   * @param {String} opts.params.oraclePublicKey
   * @param {String} opts.params.redemptionContractBaseBytecode
   * @param {Object} opts.options
   * @param {'v1' | 'v2' | 'v3'} opts.options.version
   * @param {'mainnet' | 'chipnet'} opts.options.network
   * @param {'p2sh20' | 'p2sh32'} opts.options.addressType
   */
  constructor(opts) {
    this.params = {
      authKeyId: opts?.params?.authKeyId,
      pubkeys: opts?.params?.pubkeys,
      anyhedgeBaseBytecode: opts?.params?.anyhedgeBaseBytecode,
      redemptionTokenCategory: opts?.params?.redemptionTokenCategory,
      oraclePublicKey: opts?.params?.oraclePublicKey,
      redemptionContractBaseBytecode: opts?.params?.redemptionContractBaseBytecode,
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
    let cashscriptFilename = 'treasury-contract.cash';
    if (version === 'v2') {
      cashscriptFilename = 'treasury-contract-v2.cash';
    } else if (version) {
      cashscriptFilename = `treasury-contract-${version}.cash`;
    }
    const artifact = compileFile(new URL(cashscriptFilename, import.meta.url));
    return artifact;
  }

  get contractParameters() {
    const version = this.options.version
    const contractParams = [
      hexToBin(this.params?.authKeyId).reverse(),
      hexToBin(this.params?.pubkeys?.[0]),
      hexToBin(this.params?.pubkeys?.[1]),
      hexToBin(this.params?.pubkeys?.[2]),
      hexToBin(this.params?.pubkeys?.[3]),
      hexToBin(this.params?.pubkeys?.[4]),
    ]

    if (['v2', 'v3'].includes(version)) {
      contractParams.push(
        hash256(hexToBin(this.params?.anyhedgeBaseBytecode))
      )
    }

    if (version === 'v3') {
      contractParams.push(
        hexToBin(this.params?.redemptionTokenCategory).reverse(),
        hexToBin(this.params?.oraclePublicKey),
        hash256(hexToBin(this.params?.redemptionContractBaseBytecode)),
      )
    }
    return contractParams
  }

  getContract() {
    const provider = new ElectrumNetworkProvider(this.isChipnet ? 'chipnet' : 'mainnet')
    const opts = { provider, addressType: this.options?.addressType }

    const artifact = TreasuryContract.getArtifact(this.options?.version)

    const contractParams = this.contractParameters
    const contract = new Contract(artifact, contractParams, opts);

    if (contract.opcount > 201) console.warn(`Opcount must be at most 201. Got ${contract.opcount}`)
    if (contract.bytesize > 520) console.warn(`Bytesize must be at most 520. Got ${contract.bytesize}`)

    return contract
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
        ? transaction.fromP2PKH(input, new SignatureTemplate(input.wif, HashType.SIGHASH_SINGLE | HashType.SIGHASH_ANYONECANPAY, SignatureAlgorithm.ECDSA))
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
   * @param {{ sighash: String, signature: String }[] | SignatureTemplate} opts.sig1
   * @param {{ sighash: String, signature: String }[] | SignatureTemplate} opts.sig2
   * @param {{ sighash: String, signature: String }[] | SignatureTemplate} opts.sig3
   * @param {import("cashscript").Utxo[]} opts.inputs
   * @param {import("cashscript").Recipient[]} opts.outputs
   * @param {Number} [opts.locktime]
   */
  async unlockWithMultiSig(opts) {
    /**
     * Directly passing signature as Uint8Array gives error in some cases since
     *   it expects 65bytes, but some signatures(like SignatureAlgorithm.ECDSA) gives 71bytes
     *   wrapping the signature inside a SignatureTemplate class skips the byte length checking
     */
    const sig1 = parseSigParam(opts?.sig1)
    const sig2 = parseSigParam(opts?.sig2)
    const sig3 = parseSigParam(opts?.sig3)

    const contract = this.getContract()
    const transaction = contract.functions.unlockWithMultiSig(sig1, sig2, sig3)

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
   * @param {[String, String, String]} opts.wifs
   * @param {String} opts.recipientAddress
   * @param {import("cashscript").Utxo[]} opts.contractUtxos
   * @param {Number} [opts.locktime]
   */
  async sweepMultiSig(opts) {
    const recipientAddress = opts?.recipientAddress
    const recipientTokenAddress = toTokenAddress(recipientAddress)

    const contract = this.getContract()
    const utxos = Array.isArray(opts?.contractUtxos) ? opts?.contractUtxos : await contract.getUtxos()

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

    const inputSize = calculateInputSize(contract.functions.unlockWithMultiSig(
      new Uint8Array(65).fill(255),
      new Uint8Array(65).fill(255),
      new Uint8Array(65).fill(255),
    )) + 20 // tx calculations have been off by atmost 19 bytes (so far)
    const feePerByte = 1.0

    const totalInputFeeSats = BigInt(Math.ceil((inputs.length * inputSize) * feePerByte))

    const cashtokenOutputSats =  outputs
      .reduce((subtotal, output) => {
        return subtotal + output.amount
      }, 0n)
    const cashTokenOutputFees = outputs
      .reduce((subtotal, output) => {
        const outputFee = BigInt(Math.ceil(getOutputSize(output) * feePerByte))
        return subtotal + outputFee
      }, 0n)

    const totalOutputAndFeesWithoutChange = cashtokenOutputSats + cashTokenOutputFees

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

    const totalFees = baseFeeSats + totalInputFeeSats + cashTokenOutputFees + changeOutputFee

    const transaction = await this.unlockWithMultiSig({
      inputs: inputs,
      outputs: outputs,
      sig1: new SignatureTemplate(opts?.wifs[0], undefined, SignatureAlgorithm.ECDSA),
      sig2: new SignatureTemplate(opts?.wifs[1], undefined, SignatureAlgorithm.ECDSA),
      sig3: new SignatureTemplate(opts?.wifs[2], undefined, SignatureAlgorithm.ECDSA),
      locktime: opts?.locktime,
    })
    if (typeof transaction === 'string') return transaction

    transaction.withFeePerByte(feePerByte)
    transaction.withHardcodedFee(totalFees)
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
    const utxos = Array.isArray(opts?.contractUtxos) ? opts?.contractUtxos : await contract.getUtxos()
    // const utxos = [{
    //   txid: "d6ea16eae7d6541f680752236412a75eeeb563ace677562582b0ed83fbeb4723",
    //   vout: 0,
    //   satoshis: 100000n,
    //   token: undefined,
    // }]
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


  /**
   * @param {Object} opts 
   * @param {{ sighash:String, signature:String, pubkey:String }[]} opts.sig
   * @param {Number} opts.locktime
   * @param {import("cashscript").UtxoP2PKH[]} opts.inputs
   * @param {import("cashscript").Output[]} opts.outputs
   */
  verifyMultisigTxSignature(opts) {
    const contract = this.getContract()
    const { transaction, sourceOutputs } = cashscriptTxToLibauth(contract.address, {
      version: 2,
      locktime: opts.locktime,
      inputs: opts?.inputs,
      outputs: opts?.outputs,
    })

    // we get only one, assumming all hashtypes of the signatures are the same
    const hashType = opts?.sig
      .filter(Boolean)
      .map(sigdata => hexToBin(sigdata.signature).at(-1))
      .at(0)

    const bytecode = hexToBin(contract.bytecode)

    return opts.sig.map((sigData, index) => {
      if (!sigData) return true
      
      const pubkey = hexToBin(sigData.pubkey)
      if (!this.params.pubkeys.includes(sigData.pubkey)) {
        return 'invalid_pubkey'
      }

      const preimage = createSighashPreimage(transaction, sourceOutputs, index, bytecode, hashType)
      const sighash = hash256(preimage);
      const sighashHex = binToHex(sighash)

      if (sigData.sighash !== sighashHex) return 'incorrect_sighash'

      // removed the hashtype at the end
      const signature = hexToBin(sigData.signature).slice(0, -1)
      const validSignature = secp256k1.verifySignatureDER(signature, pubkey, sighash)

      if (!validSignature) return 'invalid_signature'
  
      return validSignature
    })
  }

  /**
   * @param {Object} opts
   * @param {{ sighash: String, signature: String }[] | SignatureTemplate} opts.sig1
   * @param {{ sighash: String, signature: String }[] | SignatureTemplate} opts.sig2
   * @param {{ sighash: String, signature: String }[] | SignatureTemplate} opts.sig3
   * @param {Number} opts.locktime
   * @param {import("cashscript").UtxoP2PKH[]} opts.inputs
   * @param {import("cashscript").Recipient[]} opts.outputs
   * 
   */
  getMultisigSignatures(opts) {
    const contract = this.getContract()
    const { transaction, sourceOutputs } = cashscriptTxToLibauth(contract.address, {
      version: 2,
      locktime: opts?.locktime,
      inputs: opts?.inputs,
      outputs: opts?.outputs,
    })

    const sig1 = parseSigParam(opts?.sig1)
    const sig2 = parseSigParam(opts?.sig2)
    const sig3 = parseSigParam(opts?.sig3)

    const unlocker = contract.unlock.unlockWithMultiSig(sig1, sig2, sig3)
    return opts?.inputs?.map((input, inputIndex) => {
      if (input.template) return ''
      
      const unlockingBytecode = unlocker.generateUnlockingBytecode({
        transaction, sourceOutputs, inputIndex,
      })
      return binToHex(unlockingBytecode)
    })
  }

  /**
   * @param {Object} opts
   * @param {import("@generalprotocols/anyhedge").ContractDataV2} opts.contractData
   * @param {Number} [opts.locktime]
   * @param {import("cashscript").Utxo[]} opts.inputs
   * @param {import("cashscript").Recipient[]} opts.outputs
   */
  async spendToAnyhedge(opts) {
    const contract = this.getContract()
    if (!contract.functions.spendToAnyhedge) return 'Contract function not supported'

    const covenantParams = prepareParamForTreasuryContract(opts?.contractData)
    const transaction = contract.functions.spendToAnyhedge(...covenantParams)

    opts?.inputs?.forEach(input => {
      input?.wif
        ? transaction.fromP2PKH(input, new SignatureTemplate(input.wif))
        : transaction.from(input)
    })

    transaction.to(opts?.outputs)

    if (Number.isSafeInteger(opts?.locktime)) {
      transaction.withTime(opts?.locktime)
    }
    return transaction
  }

  /**
   * @param {Object} opts 
   * @param {Number} [opts.locktime]
   * @param {import("cashscript").UtxoP2PKH} opts.feeFunderUtxo
   * @param {import("cashscript").Output} [opts.feeFunderOutput]
   * @param {import("cashscript").Utxo[]} opts.inputs
   * @param {Boolean} [opts.sendToRedemptionContract]
   * @param {Number} [opts.satoshis] falsey value would mean to consolidate all inputs into 1 utxo
   */
  async consolidate(opts) {
    const contract = this.getContract()
    if (!contract.functions.consolidate) return 'Contract function not supported'
    if (opts?.sendToRedemptionContract && this.options.version !== 'v3') {
      return 'Consolidation to redemption contract is only supported in v3'
    }

    const feeFunderUtxo = opts?.feeFunderUtxo
    const feeFunderOutput = opts?.feeFunderOutput
    const totalSats = opts.inputs.reduce((subtotal, utxo) => subtotal + utxo.satoshis, 0n)
    const opData = numbersToCumulativeHexString([0n, ...opts?.inputs?.map(input => input.satoshis)])
    const opDataBytecode = scriptToBytecode([0x6a, hexToBin(opData)])

    let consolidateParam = undefined
    if (this.options.version === 'v3') {
      consolidateParam = opts?.sendToRedemptionContract
        ? hexToBin(this.params.redemptionContractBaseBytecode)
        : new Uint8Array(0)
    }
    const builder = new TransactionBuilder({ provider: contract.provider })
      .addInput(feeFunderUtxo, feeFunderUtxo.template.unlockP2PKH())
      .addInputs(opts.inputs, contract.unlock.consolidate(consolidateParam))

    if (feeFunderOutput) {
      builder.addOutput(feeFunderOutput)
    } else {
      builder.addOutput({
        to: feeFunderUtxo.template.unlockP2PKH().generateLockingBytecode(),
        amount: feeFunderUtxo.satoshis
      })
    }

    builder.addOutput({ to: opDataBytecode, amount: 0n })

    if (opts.satoshis) {
      builder.addOutput({ to: tc.contract.address, amount: opts.satoshis })
      builder.addOutput({ to: tc.contract.address, amount: totalSats - opts.satoshis })
    } else {
      builder.addOutput({ to: tc.contract.address, amount: totalSats })
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


/**
 * @param {{ sighash: String, signature: String }[] | SignatureTemplate} sig 
 */
function parseSigParam(sig) {
  if (sig instanceof SignatureTemplate) return sig

  // last byte of a signatures is the hashType
  const hashTypes = sig.filter(Boolean).map(sigdata => hexToBin(sigdata.signature).at(-1))

  // we get only one, assumming all hashtypes of the signatures are the same
  const hashType = hashTypes[0]

  /**
   * signature parameters use signature templates,
   * we provide the `hashType` & `generateSignature`
   * since it is what's used in the class when
   * building a tx with signature parameter(see link below)
   *
   * we expect a map <sighash, signature> since
   * each input to be signed in a transaction
   * produces a different sighash
   * 
   * https://github.com/CashScript/cashscript/blob/v0.9.2/packages/cashscript/src/Contract.ts#L156
   */
  const template = new SignatureTemplate({}, hashType)
  template.generateSignature = (sighash) => {
    const sighashHex = binToHex(sighash)
    const sigData = sig.find(sigData => sigData?.sighash == sighashHex)
    const sigHex = sigData?.signature ?? ''
    if (!sigHex) {
      // console.error('Unable to find sig for sighash', sighashHex, 'in', sig)
      throw new Error(`Unable to find sig for sighash '${sighashHex}'`)
    }
    return hexToBin(sigHex)
  }
  return template
}
