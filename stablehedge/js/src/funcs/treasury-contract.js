import { TreasuryContract } from '../contracts/treasury-contract/index.js'
import { parseUtxo } from '../utils/crypto.js'

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
