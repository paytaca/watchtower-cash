import { SignatureTemplate } from "cashscript"
import { placeholder, scriptToBytecode } from "@cashscript/utils"
import { cashScriptOutputToLibauthOutput, createInputScript, getInputSize, getPreimageSize } from "cashscript/dist/utils.js";
import { cashAddressToLockingBytecode, hexToBin } from "@bitauth/libauth";

/**
 * Taken directly from Transaction class' fee calculation
 * Returns the bytesize of contract's transaction input
 * @param {Transaction} transaction
 */
export function calculateInputSize(transaction) {
  const placeholderArgs = transaction.args.map((arg) => (arg instanceof SignatureTemplate ? placeholder(71) : arg));
  // Create a placeholder preimage of the correct size
  const placeholderPreimage = transaction.abiFunction.covenant
      ? placeholder(getPreimageSize(scriptToBytecode(transaction.contract.redeemScript)))
      : undefined;
  // Create a placeholder input script for size calculation using the placeholder
  // arguments and correctly sized placeholder preimage
  const placeholderScript = createInputScript(transaction.contract.redeemScript, placeholderArgs, transaction.selector, placeholderPreimage);
  // Add one extra byte per input to over-estimate tx-in count
  const contractInputSize = getInputSize(placeholderScript) + 1;
  return contractInputSize
}


/**
 * @param {String} contractAddress
 * @param {Object} tx 
 * @param {Number} [tx.version]
 * @param {Number} tx.locktime
 * @param {import("cashscript").UtxoP2PKH[]} tx.inputs
 * @param {import("cashscript").Output[]} tx.outputs
 */
export function cashscriptTxToLibauth(contractAddress, tx) {
  const transaction = {
    version: tx?.version || 2,
    locktime: tx?.locktime,
    inputs: tx?.inputs?.map(input => {
      return {  
        outpointIndex: input?.vout,
        outpointTransactionHash: hexToBin(input?.txid),
        sequenceNumber: 0xfffffffe,
        unlockingBytecode: new Uint8Array(),
      }
    }),
    outputs: tx?.outputs?.map(cashScriptOutputToLibauthOutput),
  }

  let contractBytecode
  const sourceOutputs = tx?.inputs?.map(input => {
    const sourceBytecode = input?.template?.unlockP2PKH()?.generateLockingBytecode?.()

    // lazy loading contractAddress' bytecode
    if (!sourceBytecode && !contractBytecode) {
      contractBytecode = cashAddressToLockingBytecode(contractAddress)
      if (typeof contractBytecode === 'string') throw new Error(contractBytecode)
      contractBytecode = contractBytecode.bytecode
    }

    const sourceOutput = {
      to: sourceBytecode || contractBytecode,
      amount: BigInt(input?.satoshis),
      token: !input?.token ? undefined : {
        category: hexToBin(input?.token?.category),
        amount: BigInt(input?.token?.amount),
        nft: !input?.token?.nft ? undefined : {
          commitment: hexToBin(input?.token?.nft?.commitment),
          capability: input?.token?.nft?.capability,
        }
      },
    }

    return cashScriptOutputToLibauthOutput(sourceOutput);
  })

  return { transaction, sourceOutputs }
}

/**
 * 
 * @param {import("cashscript").Utxo[]} utxos 
 */
export function groupUtxoAssets(utxos) {
  const assets = {
    totalSats: 0n,
    fungibleTokens: [].map(() => ({
      category: '', amount: 0n,
    })),
    nfts: [].map(() => ({
      category: '', capability: '', commitment: '',
    }))
  }

  utxos.forEach(utxo => {
    assets.totalSats += utxo.satoshis
    if (!utxo.token) return
    const token = utxo.token

    if (token.amount) {
      const tokenBalance = assets.fungibleTokens.find(tokenBal => tokenBal.category === token.category)
      if (tokenBalance) tokenBalance.amount += token.amount
      else assets.fungibleTokens.push({ category: token.category, amount: token.amount })
    }

    if (token.nft) {
      assets.nfts.push({
        category: token.category,
        capability: token.nft.capability,
        commitment: token.nft.commitment,
      })
    }
  })

  return assets
}

/**
 * @param {BigInt | Number} value 
 * @param {Number} decimals 
 */
export function addPrecision(value, decimals=4) {
  return BigInt(Number(value) * 10 ** decimals)
}

/**
 * @param {BigInt} value 
 * @param {Number} decimals 
 * @returns {BigInt}
 */
export function removePrecision(value, decimals=4) {
  return value / (10n ** BigInt(decimals))
}
