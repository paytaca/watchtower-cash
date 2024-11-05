import { TreasuryContract } from '../contracts/treasury-contract/index.js'
import { isValidWif, parseCashscriptOutput, parseUtxo, serializeOutput, serializeUtxo } from '../utils/crypto.js'
import { SignatureAlgorithm, SignatureTemplate } from 'cashscript'


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
 * @param {import('cashscript').Utxo[]} opts.inputs
 * @param {import('cashscript').Output[]} opts.outputs
 */
export async function constructTreasuryContractTx(opts) {
  const treasuryContract = new TreasuryContract(opts?.contractOpts)

  const inputs = opts?.inputs?.map(parseUtxo)
  const outputs = opts?.outputs?.map(parseCashscriptOutput)
  const transaction = await treasuryContract.unlockWithMultiSig({
    inputs, outputs,
    locktime: 0,
    sig1: new SignatureTemplate({}, undefined, SignatureAlgorithm.ECDSA),
    sig2: new SignatureTemplate({}, undefined, SignatureAlgorithm.ECDSA),
    sig3: new SignatureTemplate({}, undefined, SignatureAlgorithm.ECDSA),
  })

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
