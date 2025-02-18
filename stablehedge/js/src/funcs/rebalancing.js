import { TransactionBuilder } from 'cashscript'
import { RedemptionContract } from '../contracts/redemption-contract/index.js'
import { TreasuryContract } from '../contracts/treasury-contract/index.js'
import { parseUtxo, serializeOutput, serializeUtxo } from '../utils/crypto.js'
import { addPrecision, calculateInputSize, removePrecision } from '../utils/transaction.js'
import { getOutputSize } from 'cashscript/dist/utils.js'

/**
 * @param {Object} opts
 * @param {Object} opts.treasuryContractOpts
 * @param {Object} opts.redemptionContractOpts
 * @param {Number} opts.locktime
 * @param {Number} [opts.satoshis] Amount to transfer, undefined if transfer all
 * @param {import('cashscript').Utxo[]} opts.treasuryContractUtxos
 * @param {import('cashscript').UtxoP2PKH} opts.authKeyUtxo
 * @param {import('cashscript').Utxo} opts.reserveUtxo
 */
export async function transferTreasuryFundsToRedemptionContract(opts) {
  const treasuryContract = new TreasuryContract(opts?.treasuryContractOpts)
  const redemptionContract = new RedemptionContract(opts?.redemptionContractOpts)

  const reserveUtxo = parseUtxo(opts?.reserveUtxo)
  const authKeyUtxo = parseUtxo(opts?.authKeyUtxo)
  const treasuryContractUtxos = opts?.treasuryContractUtxos.map(parseUtxo)

  const tc = treasuryContract.getContract()
  const rc = redemptionContract.getContract()

  const tcTx = tc.functions.unlockWithNft(false)
  const rcTx = rc.functions.unlockWithNft(false)

  const tcInputSize = calculateInputSize(tcTx)
  const rcInputSize = calculateInputSize(rcTx)

  const tcUnlocker = tcTx.unlocker
  const rcUnlocker = rcTx.unlocker

  let __totalInput = addPrecision(0)
  let __totalOutput = addPrecision(0)
  let __txFee = addPrecision(10 + 2)
  const transaction = new TransactionBuilder({ provider: tc.provider })
  transaction.setLocktime(parseInt(opts?.locktime) || 0)

  transaction.addInput(reserveUtxo, rcUnlocker)
  __totalInput += addPrecision(reserveUtxo.satoshis)
  __txFee += addPrecision(tcInputSize)

  transaction.addInput(authKeyUtxo, rcUnlocker)
  __totalInput += addPrecision(authKeyUtxo.satoshis)
  __txFee += addPrecision(rcInputSize)

  transaction.addInputs(treasuryContractUtxos, tcUnlocker)
  __totalInput += treasuryContractUtxos
    .map(utxo => addPrecision(utxo.satoshis))
    .reduce((subtotal, __sats) => subtotal + __sats, 0n)
  __txFee += addPrecision(tcInputSize * treasuryContractUtxos.length)

  let changeOutput = true
  let outputSats = reserveUtxo.satoshis

  if (opts?.satoshis) {
    outputSats += BigInt(opts.satoshis)
    changeOutput = true
  } else {
    changeOutput = false
  }

  const reserveOutput = { to: rc.address, amount: outputSats, token: reserveUtxo.token }
  transaction.addOutput(reserveOutput)
  __totalOutput += addPrecision(outputSats)
  __txFee += addPrecision(getOutputSize(reserveOutput))

  const authKeyOutput = {
    to: authKeyUtxo.template.unlockP2PKH().getLockingBytecode(),
    amount: authKeyUtxo.satoshis,
    token: authKeyUtxo.token,
  }
  transaction.addOutput(authKeyOutput)
  __totalOutput += addPrecision(authKeyUtxo.satoshis)
  __txFee += addPrecision(getOutputSize(authKeyOutput))

  if(changeOutput) {
    const changeOutput = { to: tc.address, amount: 546n }
    const __changeAmount = addPrecision(changeOutput.amount)
    const __changeFee = addPrecision(getOutputSize(changeOutput))

    const __excessSats = __totalInput - __totalOutput - __txFee - __changeAmount - __changeFee
    if (__excessSats > 0) {
      changeOutput.amount += removePrecision(__excessSats)
      transaction.addOutput(changeOutput)
      __totalOutput += addPrecision(changeOutput.amount)
      __txFee += addPrecision(getOutputSize(changeOutput))
    }

  } else {
    const __excessSats = __totalInput - __totalOutput - __txFee
    reserveOutput.amount += removePrecision(__excessSats)
    __totalOutput += __excessSats
  }

  const __excessSats = __totalInput - __totalOutput - __txFee
  if (__excessSats < 0) {
    return {
      success: false,
      error: `Insufficient satoshis: ${removePrecision(__excessSats * -1n)}`,
    }
  }

  if (typeof transaction === 'string') return { success: false, error: transaction }
  return {
    success: true,
    tx_hex: await transaction.build(),
    inputs: transaction.inputs.map(input => serializeUtxo(input)),
    outputs: transaction.outputs.map(output => serializeOutput(output)),
  }
}
