import { binToHex, decodePrivateKeyWif, encodeTransaction, hexToBin, secp256k1, sha256 } from '@bitauth/libauth'
import { parseUtxo, toCashAddress, toTokenAddress } from '../utils/crypto.js'
import { addPrecision, cashscriptTxToLibauth, groupUtxoAssets, removePrecision } from '../utils/transaction.js'
import { calculateDust, getOutputSize } from 'cashscript/dist/utils.js'
import { P2PKH_INPUT_SIZE, VERSION_SIZE, LOCKTIME_SIZE } from 'cashscript/dist/constants.js'
import { HashType } from 'cashscript'

/**
 * @param {Object} opts 
 * @param {String} opts.recipientAddress
 * @param {Number} opts.locktime
 * @param {import('cashscript').UtxoP2PKH[]} opts.utxos
 */
export function sweepUtxos(opts) {
  const recipientAddress = toCashAddress(opts?.recipientAddress)
  const recipientTokenAddress = toTokenAddress(opts?.recipientAddress)

  /** @type {import('cashscript').UtxoP2PKH[]} */
  const inputs = opts?.utxos?.map(parseUtxo)
  const assets = groupUtxoAssets(inputs)

  /** @type {import('cashscript').Output[]} */
  const outputs = []
  assets.nfts.forEach(nft => {
    outputs.push({
      to: recipientTokenAddress,
      amount: 1000n,
      token: {
        category: nft.category,
        amount: 0n,
        nft: { capability: nft.capability, commitment: nft.commitment },
      },
    })
  })

  assets.fungibleTokens.forEach(fungibleToken => {
    outputs.push({
      to: recipientTokenAddress,
      amount: 1000n,
      token: { category: fungibleToken.category, amount: fungibleToken.amount },
    })
  })

  outputs.push({
    to: recipientAddress,
    amount: assets.totalSats,
  })

  // to limit confusion, each underscore prefix has added precision
  const feePerByte = 1.1
  const _feePerByte = addPrecision(feePerByte)
  const __baseFee = addPrecision(VERSION_SIZE + LOCKTIME_SIZE + 2) * _feePerByte
  const _baseFee = removePrecision(__baseFee)

  const __totalInputFeeSats = addPrecision(inputs.length * P2PKH_INPUT_SIZE) * _feePerByte
  const _totalInputFeeSats = removePrecision(__totalInputFeeSats)
  const _totalOutputFeeSats = outputs.reduce((_subtotal, output) => {
    const __outputFee = addPrecision(getOutputSize(output)) * _feePerByte
    const _outputFee = removePrecision(__outputFee)
    return _subtotal + _outputFee
  }, 0n)

  let _totalInputSats = addPrecision(inputs.reduce((subtotal, input) => subtotal + input.satoshis, 0n))
  let _totalOutputSats = addPrecision(outputs.reduce((subtotal, output) => subtotal + output.amount, 0n))
  let _totalFeeSats = _baseFee + _totalInputFeeSats + _totalOutputFeeSats

  // use sats from utxos as fee if funding utxos is not enough
  for (let index=0; index < outputs.length; index++) {
    const output = outputs[index];
    const _deficitSats = (_totalOutputSats + _totalFeeSats) - _totalInputSats
    const deficitSats =  removePrecision(_deficitSats) + 1n
    if (deficitSats < 0) break

    const dust = BigInt(calculateDust(output))
    if (output.amount <= dust) continue;

    const diff = output.amount - dust
    const deducted = deficitSats < diff  ? deficitSats : diff
    output.amount -= deducted
    _totalOutputSats -= addPrecision(deducted)
  }

  const deficitSats = removePrecision((_totalOutputSats + _totalFeeSats) - _totalInputSats) + 1n
  if (deficitSats < 0) {
    return {
      success: false,
      error: 'Insufficient fees',
      deficit: deficitSats.toString(),
    }
  }

  const { transaction, sourceOutputs } = cashscriptTxToLibauth('', {
    version: 2,
    locktime: opts.locktime,
    inputs,
    outputs,
  })

  transaction.inputs.forEach((input, inputIndex) => {
    if (input.unlockingBytecode?.length) return

    const unlocker = inputs[inputIndex].template.unlockP2PKH()
    input.unlockingBytecode = unlocker.generateUnlockingBytecode({
      transaction, sourceOutputs, inputIndex,
    })
  })

  return {
    success: true,
    transaction: binToHex(encodeTransaction(transaction)),
  }
}

/**
 * @param {Object} opts
 * @param {String} opts.wif
 * @param {String} opts.message utf8 encoded message
 */
export function schnorrSign(opts) {
  const decodedWif = decodePrivateKeyWif(opts?.wif)
  if (typeof decodedWif === 'string') return {
    success: false, error: decodedWif,
  }

  const privateKey = decodedWif.privateKey

  const msgHash = sha256.hash(Buffer.from(opts?.message, 'utf8'))
  const signature = secp256k1.signMessageHashSchnorr(privateKey, msgHash)
  return { success: true, signature: binToHex(signature) }
}

/**
 * @param {Object} opts 
 * @param {Number} opts.locktime
 * @param {import('cashscript').UtxoP2PKH} opts.authKeyUtxo
 */
export function signAuthKeyUtxo(opts) {
  const locktime = parseInt(opts?.locktime) || 0
  const authKeyUtxo = parseUtxo({
    ...opts?.authKeyUtxo,
    hashType: HashType.SIGHASH_SINGLE | HashType.SIGHASH_ANYONECANPAY,
  })


  /** @type {import('cashscript').SignatureTemplate} */
  const signatureTemplate = authKeyUtxo?.template
  const unlocker = signatureTemplate?.unlockP2PKH()
  const utxoLockingBytecode = unlocker.generateLockingBytecode()

  const transaction = {
    version: 2,
    locktime: locktime,
    inputs: [{
      outpointIndex: authKeyUtxo?.vout,
      outpointTransactionHash: hexToBin(authKeyUtxo?.txid),
      sequenceNumber: 0xfffffffe,
      unlockingBytecode: new Uint8Array(),
    }],
    outputs: [{
      lockingBytecode: utxoLockingBytecode,
      valueSatoshis: authKeyUtxo.satoshis,
      token: {
        category: hexToBin(authKeyUtxo.token.category),
        amount: authKeyUtxo.token.amount,
        nft: {
          commitment: hexToBin(authKeyUtxo.token.nft.commitment),
          capability: authKeyUtxo.token.nft.capability,
        }
      }
    }],
  }


  const sourceOutputs = [{
    lockingBytecode: utxoLockingBytecode,
    valueSatoshis: authKeyUtxo.satoshis,
    token: {
      category: hexToBin(authKeyUtxo.token.category),
      amount: authKeyUtxo.token.amount,
      nft: {
        commitment: hexToBin(authKeyUtxo.token.nft.commitment),
        capability: authKeyUtxo.token.nft.capability,
      }
    }
  }]

  const unlockingBytecode = signatureTemplate.unlockP2PKH().generateUnlockingBytecode({
    transaction,
    inputIndex: 0,
    sourceOutputs,
  })

  return {
    success: true,
    locktime,
    lockingBytecode: binToHex(utxoLockingBytecode),
    unlockingBytecode: binToHex(unlockingBytecode),
  }
}
