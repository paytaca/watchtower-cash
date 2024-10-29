import { binToHex, encodeTransaction } from '@bitauth/libauth'
import { parseUtxo, toCashAddress, toTokenAddress } from '../utils/crypto.js'
import { addPrecision, cashscriptTxToLibauth, groupUtxoAssets, removePrecision } from '../utils/transaction.js'
import { calculateDust, getOutputSize } from 'cashscript/dist/utils.js'
import { P2PKH_INPUT_SIZE, VERSION_SIZE, LOCKTIME_SIZE } from 'cashscript/dist/constants.js'

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
