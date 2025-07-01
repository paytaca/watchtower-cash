import {
  encodeTransactionCommon,
  hashTransaction,
  lockingBytecodeToCashAddress,
  walletTemplateToCompilerBch,
  CashAddressNetworkPrefix,
  generateTransaction,
  binToHex,
  extractResolvedVariables,
  utf8ToBin,
  binToBase64,
  base64ToBin,
  binToUtf8,
  hexToBin,
  stringify,
  decodeTransactionCommon,
  createVirtualMachineBch
} from 'bitauth-libauth-v3'

export class Pst {
  /**
   * Optional - signatures, template, unsignedTransaction, sourceOutputs, desc, txid
   */
  constructor ({ lockingData, network, signatures, template, unsignedTransaction, sourceOutputs, desc, txid }) {
    this.txid = txid
    this.lockingData = lockingData
    this.network = network || CashAddressNetworkPrefix.mainnet
    this.sourceOutputs = sourceOutputs
    this.desc = desc
    this.template = template
    if (unsignedTransaction) {
      const transaction = decodeTransactionCommon(hexToBin(unsignedTransaction))
      this.setTransaction(transaction)
    }
    if (signatures) {
      this.setSignatures(signatures)
    }
  }

  get id () {
    if (!this.unsignedTransaction) return
    return hashTransaction(hexToBin(this.unsignedTransaction))
  }

  get m () {
    if (!this.template) return
    const ops = this.template.scripts[this.lockingScriptId].script.split('\n')
    return Number(ops[0].split('_')[1])
  }

  get n () {
    if (!this.template) return
    const ops = this.template.scripts[this.lockingScriptId].script.split('\n')
    return Number(ops[ops.length - 2].split('_')[1])
  }

  get lockingScriptId () {
    return 'lock'
  }

  get compiler () {
    if (!this.template) return
    return walletTemplateToCompilerBch(this.template)
  }

  /**
   * Derived from locking bytecode of this locking data and template
   */
  get address () {
    if (!this.compiler) return ''
    const lockingBytecode = this.compiler.generateBytecode({
      data: this.lockingData,
      scriptId: this.lockingScriptId
    })

    const { address } = lockingBytecodeToCashAddress({
      bytecode: lockingBytecode.bytecode,
      prefix: this.network
    })
    return address
  }

  get signersInfo () {
    if (!this.template) return {}
    const signersLockingData = this.lockingData.hdKeys.hdPublicKeys // { signer_1: xPub..., .... }
    const signersInfo = {}
    for (const signer of Object.entries(signersLockingData)) {
      const [signerEntityKey, signerHdPubKey] = signer
      const template = this.template
      // only samples signatures of input 0, TODO: show sigs of each input
      const signerSignature = Object.entries(Object.values(this.signatures || {})[0]).find((signatureKeyValue) => {
        const [signatureKey/* , signatureValue */] = signatureKeyValue
        const signerEntityVariableKey = signatureKey.split('.')[0]
        return Boolean(template.entities[signerEntityKey].variables[signerEntityVariableKey])
      })
      signersInfo[signerEntityKey] = structuredClone(this.template.entities[signerEntityKey])
      signersInfo[signerEntityKey].hdPublicKey = signerHdPubKey
      if (signerSignature) {
        signersInfo[signerEntityKey].signature = Object.fromEntries([signerSignature])
      }
    }
    return signersInfo
  }

  get transaction () {
    return {
      version: this.version,
      inputs: this.inputs,
      outputs: this.outputs,
      locktime: this.locktime
    }
  }

  get unsignedTransaction () {
    if (!this.inputs && !this.outputs) return ''
    return binToHex(encodeTransactionCommon(Pst.transactionBinObjectsToUint8Array(this.transaction)))
  }

  get totalSatoshiValue () {
    return this.outputs?.reduce((total, currentOutput) => {
      total += Number(currentOutput.valueSatoshis)
      return total
    }, 0)
  }

  get totalBchValue () {
    return this.totalSatoshiValue / 1e8
  }

  get numberOfRecipients () {
    const recipients = new Set()
    this.outputs.forEach(output => {
      const { address } = lockingBytecodeToCashAddress({ bytecode: output.lockingBytecode })
      recipients.add(address)
    })
    return recipients.size
  }

  get isSignaturesComplete () {
    if (!this.m) return false
    return Object.keys(this.signatures).every((inputIndex) => {
      return Object.keys(this.signatures[inputIndex]).length >= this.m
    })
  }

  setVersion (version) {
    this.version = version || 2
    return this
  }

  setLocktime (locktime) {
    this.locktime = locktime || 0
    return this
  }

  checkIfSignaturesAreComplete () {
    const signatures = structuredClone(this.signatures)
    Object.entries(signatures).forEach((signatureEntry) => {
      const [key, value] = signatureEntry
      signatures[key] =
        typeof value === 'string' ? hexToBin(value) : Uint8Array.from(Object.values(value))
    })

    const lockingBytecode = this.compiler.generateBytecode({
      data: this.lockingData,
      scriptId: this.lockingScriptId
    })

    const { address } = lockingBytecodeToCashAddress({
      bytecode: lockingBytecode.bytecode,
      prefix: this.network
    })

    const unlockingScriptId = this.getUnlockingScriptId({ signatures: this.signatures, template: this.template })
    const transaction = structuredClone(this.transaction)
    const sourceOutputs = [] // will be used for verification
    for (const [index, input] of transaction.inputs.entries()) {
      let sourceOutput = structuredClone(input.sourceOutput)
      if (!sourceOutput) {
        sourceOutput = this.sourceOutputs.find((utxo) => {
          return utxo.outpointIndex === input.outpointIndex &&
                binToHex(Uint8Array.from(Object.values(utxo.outpointTransactionHash))) ===
                binToHex(Uint8Array.from(Object.values(input.outpointTransactionHash)))
        })
      }
      sourceOutput.lockingBytecode = Uint8Array.from(Object.values(sourceOutput.lockingBytecode))
      if (lockingBytecodeToCashAddress({ bytecode: sourceOutput.lockingBytecode, prefix: this.network }).address === address) {
        const inputUnlockingData = {
          ...this.lockingData,
          bytecode: {
            ...this.signatures[index]
          }
        }

        input.unlockingBytecode = {
          ...input.unlockingBytecode,
          compiler: this.compiler,
          data: inputUnlockingData,
          valueSatoshis: sourceOutput.valueSatoshis,
          script: unlockingScriptId,
          token: sourceOutput.token
        }
      }
      sourceOutputs.push(sourceOutput)
    }

    const successfulCompilation = generateTransaction({
      ...transaction
    })
    console.log('🚀 ~ Pst ~ checkIfSignaturesAreComplete ~ successfulCompilation:', successfulCompilation)
  }

  addInput (input, sourceOutput) {
    const _input = structuredClone(input)
    const _sourceOutput = structuredClone(sourceOutput)
    if (!_input.sourceOutput) {
      _input.sourceOutput = sourceOutput
    }
    if (_input.outpointTransactionHash && !(_input?.outpointTransactionHash instanceof Uint8Array)) {
      _input.outpointTransactionHash = Uint8Array.from(Object.values((_input.outpointTransactionHash)))
    }
    if (_input.unlockingBytecode && !(_input?.unlockingBytecode instanceof Uint8Array)) {
      _input.unlockingBytecode = Uint8Array.from(Object.values((_input.unlockingBytecode)))
    }
    this.inputs.push(structuredClone(_input))
    this.sourceOutputs.push(_sourceOutput)
    return this
  }

  addOutput (output) {
    const _output = structuredClone(output)
    if (_output.lockingBytecode && !(_output?.lockingBytecode instanceof Uint8Array)) {
      _output.lockingBytecode = Uint8Array.from(Object.values(_output.lockingBytecode))
    }
    this.outputs.push(_output)
    return this
  }

  setTemplate (template) {
    this.template = template
    return this
  }

  setSignatures (signatures) {
    const sigs = structuredClone(signatures)
    Object.keys(sigs).forEach((inputIndex) => {
      Object.keys(sigs[inputIndex]).forEach((signatureKey) => {
        if (typeof sigs[inputIndex][signatureKey] === 'string') {
          sigs[inputIndex][signatureKey] = hexToBin(sigs[inputIndex][signatureKey])
        }
      })
    })
    this.signatures = sigs
  }

  setTransaction (transaction) {
    const t = Pst.transactionBinObjectsToUint8Array(structuredClone(transaction))
    // TODO: REMOVE, TESTING RELAY FEE ERROR
    // const beforeSatoshi = t.outputs[1].valueSatoshis
    // console.log('🚀 ~ Pst ~ setTransaction ~ t.outputs[1]:', beforeSatoshi)
    // t.outputs[1].valueSatoshis = BigInt(t.outputs[1].valueSatoshis) - BigInt(2000)
    // console.log('🚀 ~ Pst ~ setTransaction ~ t.outputs[1] AFTER:', t.outputs[1])
    this.inputs = t.inputs
    this.outputs = t.outputs
    this.version = t.version
    this.locktime = t.locktime
    return this
  }

  setSourceOutputs (sourceOutputs) {
    const _sourceOutputs = structuredClone(sourceOutputs)
    _sourceOutputs.forEach((utxo) => {
      if (utxo.outpointTransactionHash) {
        utxo.outpointTransactionHash = Uint8Array.from(Object.values(utxo.outpointTransactionHash))
      }
      utxo.lockingBytecode = Uint8Array.from(Object.values(utxo.lockingBytecode))
    })
    this.sourceOutputs = _sourceOutputs
    return this
  }

  setDesc (desc) {
    this.desc = desc
    return this
  }

  signTransaction (entityPrivateKey /* example: { signer_1: privatekeyofsigner1 } */) {
    const [entity, privateKey] = Object.entries(entityPrivateKey)[0]
    const entityUnlockingData = {
      ...this.lockingData,
      hdKeys: {
        ...this.lockingData.hdKeys,
        hdPrivateKeys: {
          [entity]: privateKey
        }
      }
    }
    console.log('🚀 ~ Pst ~ signTransaction ~ entityUnlockingData:', entityUnlockingData)

    const unlockingScriptId = this.template.entities[entity].scripts.filter((scriptId) => scriptId !== 'lock')[0]
    console.log('unlockingScriptId', unlockingScriptId)
    const transaction = structuredClone(this.transaction)
    for (const input of transaction.inputs) {
      let sourceOutput = input.sourceOutput

      if (!sourceOutput) {
        sourceOutput = this.sourceOutputs.find((utxo) => {
          return utxo.outpointIndex === input.outpointIndex && binToHex(Uint8Array.from(Object.values(utxo.outpointTransactionHash))) === binToHex(Uint8Array.from(Object.values(input.outpointTransactionHash)))
        })
      }
      const { address: sourceOutputAddress } = lockingBytecodeToCashAddress({ bytecode: Uint8Array.from(Object.values(sourceOutput.lockingBytecode)), prefix: this.network })
      if (sourceOutputAddress === this.address) {
        input.unlockingBytecode = {
          // ...input.unlockingBytecode,
          compiler: this.compiler,
          data: entityUnlockingData,
          valueSatoshis: sourceOutput.valueSatoshis,
          script: unlockingScriptId,
          token: sourceOutput.token
        }
      }
    }

    const signAttempt = generateTransaction({ ...transaction })
    if (!this.signatures) {
      this.signatures = {}
    }
    console.log('🚀 ~ Pst ~ signTransaction ~ signAttempt:', stringify(signAttempt))

    for (const [index, error] of Object.entries(signAttempt.errors)) {
      if (!this.signatures[index]) {
        this.signatures[index] = {}
      }
      const signerResolvedVariables = extractResolvedVariables({ ...signAttempt, errors: [error] })
      const signatureKey = Object.keys(signerResolvedVariables)[0]
      const signatureValue = Object.values(signerResolvedVariables)[0]
      this.signatures[index][signatureKey] = signatureValue
    }

    Object.keys(this.signatures).forEach((inputIndex) => {
      Object.keys(this.signatures[inputIndex]).forEach((signatureKey) => {
        this.signatures[inputIndex][signatureKey] = Uint8Array.from(Object.values(this.signatures[inputIndex][signatureKey]))
      })
    })
    return this
  }

  getUnlockingScriptId ({ signatures, template }) {
    return Pst.getUnlockingScriptId({ signatures, template })
  }

  finalize () {
    const signatures = structuredClone(this.signatures)
    Object.entries(signatures).forEach((signatureEntry) => {
      const [key, value] = signatureEntry
      signatures[key] =
        typeof value === 'string' ? hexToBin(value) : Uint8Array.from(Object.values(value))
    })

    const lockingBytecode = this.compiler.generateBytecode({
      data: this.lockingData,
      scriptId: this.lockingScriptId
    })

    const { address } = lockingBytecodeToCashAddress({
      bytecode: lockingBytecode.bytecode,
      prefix: this.network
    })

    const unlockingScriptId = this.getUnlockingScriptId({ signatures: this.signatures, template: this.template })
    const transaction = structuredClone(this.transaction)
    const sourceOutputs = [] // will be used for verification
    for (const [index, input] of transaction.inputs.entries()) {
      let sourceOutput = input.sourceOutput
      if (!sourceOutput) {
        sourceOutput = this.sourceOutputs.find((utxo) => {
          return utxo.outpointIndex === input.outpointIndex &&
                binToHex(Uint8Array.from(Object.values(utxo.outpointTransactionHash))) ===
                binToHex(Uint8Array.from(Object.values(input.outpointTransactionHash)))
        })
      }
      sourceOutput.lockingBytecode = Uint8Array.from(Object.values(sourceOutput.lockingBytecode))
      if (lockingBytecodeToCashAddress({ bytecode: sourceOutput.lockingBytecode, prefix: this.network }).address === address) {
        const inputUnlockingData = {
          ...this.lockingData,
          bytecode: {
            ...this.signatures[index]
          }
        }

        input.unlockingBytecode = {
          ...input.unlockingBytecode,
          compiler: this.compiler,
          data: inputUnlockingData,
          valueSatoshis: sourceOutput.valueSatoshis,
          script: unlockingScriptId,
          token: sourceOutput.token
        }
      }
      sourceOutputs.push(sourceOutput)
    }

    const successfulCompilation = generateTransaction({
      ...transaction
    })
    if (successfulCompilation.success) {
      const encodedTransaction = encodeTransactionCommon(successfulCompilation.transaction)
      this.signedTransaction = binToHex(encodedTransaction)
    }

    const vm = createVirtualMachineBch()
    const verificationResult = vm.verify({
      sourceOutputs: sourceOutputs, transaction: successfulCompilation.transaction
    })
    console.log('🚀 ~ Pst ~ finalize ~ verificationResult:', verificationResult)

    Object.keys(this.signatures).forEach((inputIndex) => {
      Object.keys(this.signatures[inputIndex]).forEach((signatureKey) => {
        this.signatures[inputIndex][signatureKey] = Uint8Array.from(Object.values(this.signatures[inputIndex][signatureKey]))
      })
    })
    console.log('🚀 ~ Pst ~ finalize ~ verificationResult:', verificationResult)

    console.log('signatures', stringify(this.signatures))
    if (verificationResult !== true) {
      throw new Error('Transaction failed local vm verification')
    }
    return successfulCompilation
  }

  save (store) {
    store(this.toJSON())
  }

  update (store) {
    store(this.toJSON())
  }

  toBase64 () {
    const bin = utf8ToBin(JSON.stringify(this.toJSON()))
    return binToBase64(bin)
  }

  toBase64FromJsonSafe () {
    const bin = utf8ToBin(stringify(this.toJSON()))
    return binToBase64(bin)
  }

  toJSON () {
    const signatures = structuredClone(this.signatures)
    Object.keys(signatures).forEach((inputIndex) => {
      Object.keys(signatures[inputIndex]).forEach((signatureKey) => {
        signatures[inputIndex][signatureKey] =
          binToHex(Uint8Array.from(Object.values(signatures[inputIndex][signatureKey])))
      })
    })
    return {
      id: this.id,
      lockingData: this.lockingData,
      template: this.template,
      network: this.network,
      unsignedTransaction: this.unsignedTransaction,
      signatures: signatures,
      desc: this.desc,
      signersInfo: this.signersInfo,
      sourceOutputs: this.sourceOutputs
    }
  }

  /**
   * Combine signatures of psts
   */
  combine ({ psts }) {
    const combined = Pst.combine({ psts: [this, ...psts], expectedPstId: this.id })
    this.signatures = combined.signatures
  }

  async toPstFile (filename) {
    const jsonString = stringify(this.toJSON(), 0)
    if (typeof window !== 'undefined' && typeof window.document !== 'undefined') {
      const blob = new Blob([jsonString], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${filename}.ppst`
      a.click()
      URL.revokeObjectURL(url)
      return
    }

    try {
      const fs = await import('fs')
      fs.writeFileSync(`${filename}.ppst`, jsonString)
    } catch (error) {
      console.error('Environment not supported for file saving')
    }
  }

  static getUnlockingScriptId ({ signatures, template }) {
    const scriptsEntries = Object.entries(template.scripts)
    const unlockingScript = scriptsEntries.find(([scriptId, value]) => {
      let found = value.unlocks && scriptId !== 'lock'
      found = Object.keys(signatures).every((signatureKey) => {
        return value.script.includes(signatureKey)
      }) // Example signatureKey = key2.ecdsa_signature.all_outputs

      return found
    })
    return unlockingScript[0]
  }

  static createInstanceFromJSON (stringifiedPst) {
    return new Pst(JSON.parse(stringifiedPst))
  }

  static createInstanceFromObject (pstData) {
    if (typeof (pstData) === 'string') { return Pst.fromJSON(pstData) }
    return new Pst(pstData)
  }

  static createInstanceFromBase64 (pstData) {
    if (typeof (pstData) !== 'string') return
    const bin = base64ToBin(pstData)
    const parsed = JSON.parse(binToUtf8(bin))
    return new Pst(parsed)
  }

  /**
   * Transform a transaction's bin values in object forms to Uint8Arrays
   * @return A copy of the transaction object
   */
  static transactionBinObjectsToUint8Array (transactionObject) {
    const transaction = transactionObject
    transaction.inputs.forEach(input => {
      if (input.outpointTransactionHash && !(input?.outpointTransactionHash instanceof Uint8Array)) {
        input.outpointTransactionHash = Uint8Array.from(Object.values((input.outpointTransactionHash)))
      }
      if (input.unlockingBytecode && !(input?.unlockingBytecode instanceof Uint8Array)) {
        input.unlockingBytecode = Uint8Array.from(Object.values((input.unlockingBytecode)))
      }
      if (input.sourceOutput?.lockingBytecode && !(input.sourceOutput.lockingBytecode instanceof Uint8Array)) {
        input.lockingBytecode = Uint8Array.from(Object.values((input.sourceOutput.lockingBytecode)))
      }
    })
    transaction.outputs.forEach(output => {
      if (output.lockingBytecode && !(output?.lockingBytecode instanceof Uint8Array)) {
        output.lockingBytecode = Uint8Array.from(Object.values(output.lockingBytecode))
      }
      if (output.token?.category && !(output.token?.category instanceof Uint8Array)) {
        output.token.category = Uint8Array.from(Object.values(output.token.category))
      }

      if (output.token?.nft?.commitment && !(output.token.nft.commitment instanceof Uint8Array)) {
        output.token.nft.commitment = Uint8Array.from(Object.values(output.token.nft.commitment))
      }
    })
    return {
      version: transaction.version,
      locktime: transaction.locktime,
      inputs: transaction.inputs,
      outputs: transaction.outputs
    }
  }

  static combineSignatures (objectsArray) {
    const result = {
      sigs: {}
    }

    const indices = [...new Set(
      objectsArray.flatMap(obj => Object.keys(obj.sigs))
    )]

    indices.forEach(index => {
      const entries = objectsArray
        .filter(obj => obj.sigs[index])
        .map(obj => Object.entries(obj.sigs[index]))
        .flat()

      const seen = new Map()
      for (const [key, value] of entries) {
        if (seen.has(key)) {
          if (seen.get(key) !== value) {
            throw new Error(`Conflict detected at sigs[${index}]: key "${key}" has different values ("${seen.get(key)}" vs "${value}")`)
          }
        } else {
          seen.set(key, value)
        }
      }

      result.sigs[index] = objectsArray
        .filter(obj => obj.sigs[index])
        .reduce((combined, obj) => ({
          ...combined,
          ...obj.sigs[index]
        }), {})
    })

    return result
  }

  /**
   * Combine multiple Pst object instances.
   * @param {string} expectedPstId The expected id of all Psts
   */
  static combine ({ psts, expectedPstId }) {
    const pstWithCompleteSigs = psts.find(pst => pst.isSignaturesComplete)
    if (pstWithCompleteSigs) return pstWithCompleteSigs
    const pstWithMostSigs = psts.reduce((maxObj, currentObj) => {
      const currentSigLength = Object.keys(currentObj.signatures?.[0] || {}).length
      const maxSigLength = Object.keys(maxObj.signatures?.[0] || {}).length
      return currentSigLength > maxSigLength ? currentObj : maxObj
    })
    let compareId = expectedPstId
    if (!compareId) {
      compareId = pstWithMostSigs.id
    }
    const sameIds = psts.every(pst => pst.id === compareId)
    if (!sameIds) throw new Error('All psts must have the same ids')
    const signatures = psts.map((pst) => {
      return pst.signatures
    })
    const combinedPst = structuredClone(pstWithCompleteSigs)
    combinedPst.signatures = signatures
    return combinedPst
  }
}
