import {
  isHex,
  hexToBin,
  secp256k1,
  decodePrivateKeyWif,
  base64ToBin,
  sha256,
  binToHex,
} from "@bitauth/libauth"

import { wifToPubkey } from './crypto.js'
import { intToHexString } from './math.js'

export const MOCK_ORACLE_WIF='Kzf85aCzLmV4Ag9hjjn7RMZMHLHwdkW6Uq6yKoDxmoArr1UAizYv'
export const MOCK_ORACLE_WIF2='L3jt91Xu5guFARqPQC3c4mJnkbXZczinNY7aTKicaFyomBc2gxbh'
export const mockOracleWifs = [
  MOCK_ORACLE_WIF,
  MOCK_ORACLE_WIF2,
]


export function verifyPriceMessage(priceMessage, signature, publicKey) {
  const messageHash = sha256.hash(hexToBin(priceMessage))
  return secp256k1.verifySignatureSchnorr(
    base64ToBin(signature), hexToBin(publicKey), messageHash
  )
}

export function decodePriceMessage(priceMessage='') {
  if (!isHex(priceMessage)) return 'Invalid encoding'
  if (priceMessage?.length !== 32) return 'Invalid byte length, expected 16 bytes'


  const reverseHex = (hexStr) => {
    const bytes = hexStr.match(/.{1,2}/g);
    bytes.reverse();
    return bytes.join('');
  }

  const timestampHex = reverseHex(priceMessage.substring(0, 8))
  const msgSequenceHex = reverseHex(priceMessage.substring(8, 16))
  const dataSequenceHex = reverseHex(priceMessage.substring(16, 24))
  const priceHex = reverseHex(priceMessage.substring(24, 32))

  return {
    timestamp: parseInt(timestampHex, 16),
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
 * @param {String} opts.priceMessage
 * @param {String} opts.wif
 */
export function signPriceMessage(opts) {
  const messageHash = sha256.hash(hexToBin(opts?.priceMessage))
  const signatureBin = secp256k1.signMessageHashSchnorr(
    decodePrivateKeyWif(opts?.wif).privateKey,
    messageHash,
  )
  return signatureBin
}

/**
 * @param {Object} opts
 * @param {Number} opts.mockWifIndex
 * @param {String} opts.wif
 * @param {Number} opts.price
 */
export function generatePriceMessage(opts) {
  const mockOracleWif = mockOracleWifs[parseInt(opts?.mockWifIndex) || 0]
  const wif = opts?.wif || mockOracleWif
  const pubkey = wifToPubkey(wif)

  const priceData = {
    timestamp: Math.floor(Date.now() / 1000),
    msgSequence: Math.floor(Date.now() / 60_000),
    dataSequence: Math.floor(Date.now() / 60_000),
    price: opts?.price || Math.floor(Math.random() * 2 ** 32),
  }
  const priceMessage = constructPriceMessage(priceData)
  const signature = binToHex(signPriceMessage({ priceMessage, wif }))

  return {
    privateKey: wif,
    publicKey: pubkey,
    priceMessage: priceMessage,
    priceData: priceData,
    signature: signature,
  }
}
