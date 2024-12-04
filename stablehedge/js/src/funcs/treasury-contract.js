import { HashType, SignatureAlgorithm, SignatureTemplate } from 'cashscript'
import { binToHex, decodePrivateKeyWif, hash256, hexToBin, secp256k1, SigningSerializationFlag } from '@bitauth/libauth';
import { createSighashPreimage } from 'cashscript/dist/utils.js';
import { cashscriptTxToLibauth } from '../utils/transaction.js';
import { TreasuryContract } from '../contracts/treasury-contract/index.js'
import { isValidWif, parseCashscriptOutput, parseUtxo, serializeOutput, serializeUtxo, wifToPubkey } from '../utils/crypto.js'


export function getTreasuryContractArtifact() {
  const artifact = TreasuryContract.getArtifact();
  return { success: true, artifact }
}

/**
 * @param {Object} opts 
 */
export function compileTreasuryContract(opts) {
  const treasuryContract = new TreasuryContract(opts)
  const contract = treasuryContract.getContract()
  return {
    address: contract.address,
    tokenAddress: contract.tokenAddress,
    params: treasuryContract.params,
    options: treasuryContract.options,
    bytecode: contract.bytecode,
  }
}

/**
 * @param {Object} opts 
 * @param {Object} opts.contractOpts 
 * @param {import('cashscript').UtxoP2PKH} opts.authKeyUtxo 
 * @param {import('cashscript').UtxoP2PKH[]} opts.contractUtxos
 * @param {import('cashscript').UtxoP2PKH} opts.recipientAddress
 * @param {import('cashscript').UtxoP2PKH} opts.authKeyRecipient
 * @param {Number} [opts.locktime]
 */
export async function sweepTreasuryContract(opts) {
  const treasuryContract = new TreasuryContract(opts?.contractOpts)
  const authKeyUtxo = parseUtxo(opts?.authKeyUtxo)
  let contractUtxos = undefined
  if (opts?.contractUtxos?.length) contractUtxos = opts.contractUtxos.map(parseUtxo)
  const transaction = await treasuryContract.sweep({
    contractUtxos,
    authKeyUtxo, 
    recipientAddress: opts?.recipientAddress,
    authKeyRecipient: opts?.authKeyRecipient,
  })
  if (typeof transaction === 'string') return { success: false, error: transaction }
  return { success: true, tx_hex: await transaction.build() }
}

/**
 * @param {Object} opts
 * @param {Object} opts.contractOpts
 * @param {import('cashscript').Utxo[]} opts.inputs
 * @param {import('cashscript').Output} opts.outputs
 * @param {{ sighash: String, signature: String }[] | String} opts.sig1
 * @param {{ sighash: String, signature: String }[] | String} opts.sig2
 * @param {{ sighash: String, signature: String }[] | String} opts.sig3
 * @param {Number} [opts.locktime]
 */
export async function unlockTreasuryContractWithMultiSig(opts) {
  const treasuryContract = new TreasuryContract(opts?.contractOpts)

  const inputs = opts?.inputs?.map(parseUtxo)
  const outputs = opts?.outputs?.map(parseCashscriptOutput)

  const transaction = await treasuryContract.unlockWithMultiSig({
    inputs, outputs,
    sig1: !isValidWif(opts?.sig1) ? opts?.sig1 : new SignatureTemplate(opts?.sig1, undefined, SignatureAlgorithm.ECDSA),
    sig2: !isValidWif(opts?.sig2) ? opts?.sig2 : new SignatureTemplate(opts?.sig2, undefined, SignatureAlgorithm.ECDSA),
    sig3: !isValidWif(opts?.sig3) ? opts?.sig3 : new SignatureTemplate(opts?.sig3, undefined, SignatureAlgorithm.ECDSA),
    locktime: opts?.locktime,
  })

  if (typeof transaction === 'string') return { success: false, error: transaction }
  return { success: true, tx_hex: await transaction.build() }
}


/**
 * @param {Object} opts
 * @param {Object} opts.contractOpts
 * @param {Boolean} [opts.keepGuarded]
 * @param {import('cashscript').Utxo[]} opts.inputs
 * @param {import('cashscript').Output} opts.outputs
 * @param {Number} [opts.locktime]
 */
export async function unlockTreasuryContractWithNft(opts) {
  const treasuryContract = new TreasuryContract(opts?.contractOpts)

  const inputs = opts?.inputs?.map(parseUtxo)
  const outputs = opts?.outputs?.map(parseCashscriptOutput)

  const transaction = await treasuryContract.unlockWithNft({
    keepGuarded: opts?.keepGuarded,
    inputs, outputs,
    locktime: opts?.locktime,
  })

  if (typeof transaction === 'string') return { success: false, error: transaction }
  return { success: true, tx_hex: await transaction.build() }
}


/**
 * @param {Object} opts
 * @param {Object} opts.contractOpts 
 * @param {Boolean} [opts.multiSig=false]
 * @param {Number} [opts.locktime=0]
 * @param {import('cashscript').Utxo[]} opts.inputs
 * @param {import('cashscript').Output[]} opts.outputs
 */
export async function constructTreasuryContractTx(opts) {
  const treasuryContract = new TreasuryContract(opts?.contractOpts)

  const inputs = opts?.inputs?.map(parseUtxo)
  const outputs = opts?.outputs?.map(parseCashscriptOutput)

  let transaction 
  if (opts?.multiSig) {
    transaction = await treasuryContract.unlockWithMultiSig({
      inputs, outputs,
      locktime: Number.isSafeInteger(opts?.locktime) ? opts?.locktime : 0,
      sig1: new SignatureTemplate({}, undefined, SignatureAlgorithm.ECDSA),
      sig2: new SignatureTemplate({}, undefined, SignatureAlgorithm.ECDSA),
      sig3: new SignatureTemplate({}, undefined, SignatureAlgorithm.ECDSA),
    })
  } else {
    transaction = await treasuryContract.unlockWithNft({
      inputs, outputs,
      locktime: Number.isSafeInteger(opts?.locktime) ? opts?.locktime : 0,
      keepGuarded: false,
    })
  }
  transaction.setInputsAndOutputs();

  return {
    inputs: transaction.inputs.map(serializeUtxo),
    outputs: transaction.outputs.map(serializeOutput),
  }
}

/**
 * @param {Object} opts
 * @param {Object} opts.contractOpts 
 * @param {{ sighash:String, signature: String, pubkey: String }[]} opts.sig
 * @param {Number} opts.locktime
 * @param {import('cashscript').Utxo[]} opts.inputs
 * @param {import('cashscript').Output[]} opts.outputs
 */
export function verifyTreasuryContractMultisigTx(opts) {
  const treasuryContract = new TreasuryContract(opts?.contractOpts)

  const inputs = opts?.inputs?.map(parseUtxo)
  const outputs = opts?.outputs?.map(parseCashscriptOutput)

  const sigcheck = treasuryContract.verifyMultisigTxSignature({
    inputs, outputs,
    locktime: opts?.locktime,
    sig: opts?.sig,
  })

  const validSignatures = sigcheck.every(inputSigCheck => inputSigCheck === true)

  return { success: true, valid: validSignatures, sigcheck: sigcheck }
}

/**
 * @param {Object} opts
 * @param {Object} opts.contractOpts 
 * @param {{ sighash: String, signature: String }[] | String} opts.sig1
 * @param {{ sighash: String, signature: String }[] | String} opts.sig2
 * @param {{ sighash: String, signature: String }[] | String} opts.sig3
 * @param {Number} opts.locktime
 * @param {import('cashscript').Utxo[]} opts.inputs
 * @param {import('cashscript').Output[]} opts.outputs
 */
export function getMultisigTxUnlockingScripts(opts) {
  const treasuryContract = new TreasuryContract(opts?.contractOpts)

  const inputs = opts?.inputs?.map(parseUtxo)
  const outputs = opts?.outputs?.map(parseCashscriptOutput)

  const scriptSigs = treasuryContract.getMultisigSignatures({
    sig1: !isValidWif(opts?.sig1) ? opts?.sig1 : new SignatureTemplate(opts?.sig1, undefined, SignatureAlgorithm.ECDSA),
    sig2: !isValidWif(opts?.sig2) ? opts?.sig2 : new SignatureTemplate(opts?.sig2, undefined, SignatureAlgorithm.ECDSA),
    sig3: !isValidWif(opts?.sig3) ? opts?.sig3 : new SignatureTemplate(opts?.sig3, undefined, SignatureAlgorithm.ECDSA),
    inputs, outputs,
    locktime: opts?.locktime,
  })

  return { success: true, scripts: scriptSigs }
}

/**
 * @param {Object} opts 
 * @param {Object} opts.contractOpts
 * @param {String} opts.wif
 * @param {Number} opts.locktime
 * @param {Number} [opts.hashType]
 * @param {import('cashscript').Utxo[]} opts.inputs
 * @param {import('cashscript').Output[]} opts.outputs
 */
export function signMutliSigTx(opts) {
  const treasuryContract = new TreasuryContract(opts?.contractOpts)
  const contract = treasuryContract.getContract()
  const decodedWif = decodePrivateKeyWif(opts?.wif)
  const privateKey = decodedWif.privateKey
  const pubkey = wifToPubkey(opts?.wif)

  const inputs = opts?.inputs?.map(parseUtxo)
  const outputs = opts?.outputs?.map(parseCashscriptOutput)

  const { sourceOutputs, transaction } = cashscriptTxToLibauth(contract.address, {
    version: 2,
    locktime: opts?.locktime,
    inputs, outputs
  })

  const _hashType = opts?.hashType ? opts?.hashType : HashType.SIGHASH_ALL | HashType.SIGHASH_UTXOS;  
  const hashType = _hashType | SigningSerializationFlag.forkId

  const signatures = [].map(() => ({ sighash: '', signature: '', pubkey: '' }))
    const bytecode = hexToBin(contract.bytecode)
    transaction.inputs.forEach((input, index) => {
      if (input?.unlockingBytecode?.length > 0) return

      const preimage = createSighashPreimage(transaction, sourceOutputs, index, bytecode, hashType)
      const sighash = hash256(preimage);
      // const _signature = secp256k1.signMessageHashCompact(privateKey, sighash)
      // const _signature = secp256k1.signMessageHashSchnorr(privateKey, sighash)
      const _signature = secp256k1.signMessageHashDER(privateKey, sighash)
      const signature = Uint8Array.from([..._signature, hashType])
      const signatureHex = binToHex(signature)
      signatures[index] = {
        sighash: binToHex(sighash),
        signature: signatureHex,
        pubkey: pubkey,
      }
    })

    return signatures
}
