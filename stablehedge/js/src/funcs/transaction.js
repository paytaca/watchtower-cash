import { binToHex } from '@bitauth/libauth'
import { hash256 } from '@cashscript/utils';
import { parseCashscriptOutput, parseUtxo } from '../utils/crypto.js'
import { cashscriptTxToLibauth } from '../utils/transaction.js'
import { createSighashPreimage, publicKeyToP2PKHLockingBytecode } from 'cashscript/dist/utils.js'

/**
 * @param {Object} opts
 * @param {Number} opts.locktime
 * @param {import('cashscript').UtxoP2PKH[]} opts.inputs
 * @param {import('cashscript').Output} opts.outputs
 */
export function generateSignatures(opts) {
  /** @type {import('cashscript').UtxoP2PKH[]} */
  const inputs = opts?.inputs?.map(parseUtxo)
  const outputs = opts?.outputs?.map(parseCashscriptOutput)

  const cashscriptTx = {
    version: 2,
    locktime: opts.locktime,
    inputs: inputs,
    outputs: outputs,
  }

  const _ = 'bchtest:qq4sh33hxw2v23g2hwmcp369tany3x73wuveuzrdz5'
  const { transaction, sourceOutputs } = cashscriptTxToLibauth(_, cashscriptTx)
  const signatures = inputs.map((input, inputIndex) => {
    const template = input?.template
    if (!template) return ''

    const publicKey = template.getPublicKey();
    const prevOutScript = publicKeyToP2PKHLockingBytecode(publicKey);
    const hashtype = template.getHashType();
    const preimage = createSighashPreimage(transaction, sourceOutputs, inputIndex, prevOutScript, hashtype);
    const sighash = hash256(preimage);
    const signature = template.generateSignature(sighash);
    
    return binToHex(signature);
  });

  return { success: true, signatures }
}
