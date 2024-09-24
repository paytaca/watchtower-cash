import {
  isHex,
  hexToBin,
  binToBase64,
  secp256k1,
  decodePrivateKeyWif,
  base64ToBin,
  sha256,
} from "@bitauth/libauth"

import { wifToPubkey } from './crypto.js'
import { intToHexString } from './math.js'

const MOCK_ORACLE_WIF='Kzf85aCzLmV4Ag9hjjn7RMZMHLHwdkW6Uq6yKoDxmoArr1UAizYv'


export function verifyPriceMessage(priceMessage, signature, publicKey) {
  const messageHash = sha256.hash(hexToBin(priceMessage))
  return secp256k1.verifySignatureSchnorr(
    base64ToBin(signature), hexToBin(publicKey), messageHash
  )
}

export function decodePriceMessage(priceMessage='') {
  if (!isHex(priceMessage)) return 'Invalid encoding'
  if (priceMessage?.length !== 32) return 'Invalid byte length, expected 16 bytes'

  const timestampHex = priceMessage.substring(0, 4)
  const msgSequenceHex = priceMessage.substring(4, 8)
  const dataSequenceHex = priceMessage.substring(8, 12)
  const priceHex = priceMessage.substring(12, 16)

  return {
    timestamp: parseInt(timestampHex, 16) * 1000,
    msgSequence: parseInt(msgSequenceHex, 16),
    dataSequence: parseInt(dataSequenceHex, 16),
    price: parseInt(priceHex, 16),
  }
}

/**
 * @param {Object} opts
 * @param {Number} opts.timestamp
 * @param {Number} opts.msgSequence
 * @param {Number} opts.dataSequence
 * @param {Number} opts.price
 */
export function constructPriceMessage(opts) {
  const timestampHex = intToHexString(opts?.timestamp, 4) 
  const msgSequenceHex = intToHexString(opts?.msgSequence, 4) 
  const dataSequenceHex = intToHexString(opts?.dataSequence, 4)
  const priceHex = intToHexString(opts?.price, 4)
  return timestampHex + msgSequenceHex + dataSequenceHex + priceHex
}

/**
 * @param {Object} opts
 * @param {String} opts.wif
 * @param {Number} opts.price
 */
export function generatePriceMessage(opts) {
  const wif = opts?.wif || MOCK_ORACLE_WIF
  const pubkey = wifToPubkey(wif)

  const priceData = {
    timestamp: Math.floor(Date.now() / 1000),
    msgSequence: Math.floor(Date.now() / 60_000),
    dataSequence: Math.floor(Date.now() / 60_000),
    price: opts?.price || Math.floor(Math.random() * 2 ** 32),
  }
  const priceMessage = constructPriceMessage(priceData)
  const messageHash = sha256.hash(hexToBin(priceMessage))
  const signatureBin = secp256k1.signMessageHashSchnorr(
    decodePrivateKeyWif(wif).privateKey,
    messageHash,
  )
  const signature = binToBase64(signatureBin)

  return {
    privateKey: wif,
    publicKey: pubkey,
    priceMessage: priceMessage,
    priceData: priceData,
    signature: signature,
  }
}
