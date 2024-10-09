import crypto from 'crypto'
import {
  cashAddressToLockingBytecode,
  encodeBase58Address,
  decodeBase58Address,
  lockingBytecodeToBase58Address,
  encodePrivateKeyWif,
  generatePrivateKey,
  decodePrivateKeyWif,
  decodeCashAddress,
  CashAddressType,
  encodeCashAddress,
  secp256k1,
  ripemd160,
  binToHex,
  hexToBin,
  base64ToBin,
  binToBase58,
  isHex,
} from '@bitauth/libauth'
import { SignatureTemplate } from 'cashscript'
import { templateFromUnlockingBytecode } from './signature-template.js'


export function isValidWif(value='') {
  return /^[5KL][1-9A-HJ-NP-Za-km-z]{50,51}$/.test(value)
}

export function sha256(data='', encoding='utf8') {
  const _sha256 = crypto.createHash('sha256')
  _sha256.update(Buffer.from(data, encoding))
  return _sha256.digest().toString('hex')
}

export function toTokenAddress(address ='') {
  const decodedAddress = decodeCashAddress(address)
  if (typeof decodedAddress == 'string') throw decodedAddress
  const addrType = decodedAddress.type
  const payload = decodedAddress.payload
  switch(addrType) {
    case (CashAddressType.p2pkhWithTokens):
    case (CashAddressType.p2shWithTokens):
      return address
    case (CashAddressType.p2pkh):
      return encodeCashAddress(decodedAddress.prefix, CashAddressType.p2pkhWithTokens, payload)
    case (CashAddressType.p2sh):
      return encodeCashAddress(decodedAddress.prefix, CashAddressType.p2shWithTokens, payload)
  }
}

export function toLegacyAddress(address='') {
  const lockingBytecode = cashAddressToLockingBytecode(address) 
  if (typeof lockingBytecode === 'string') throw lockingBytecode

  const legacyAddress = lockingBytecodeToBase58Address(lockingBytecode.bytecode)
  if (typeof legacyAddress !== 'string') {
    return encodeBase58Address(legacyAddress.type, legacyAddress.payload)
  }
  return legacyAddress
}

export function addressToPkHash(address='') {
  const legacyAddress = toLegacyAddress(address)

  // Decode the Base58Check-encoded legacy address
  const decodedLegacyAddress = decodeBase58Address(legacyAddress)
  if (typeof decodedLegacyAddress === 'string') throw decodedLegacyAddress

  return binToHex(decodedLegacyAddress.payload);
}

export function pubkeyToPkHash(pubkey='') {
  return binToHex(ripemd160.hash(hexToBin(sha256(pubkey, 'hex'))))
}

export function pkHashToLegacyAddress(pkhash='') {
  const pkHashBin = Buffer.from(pkhash, 'hex')
  const versionByte = Buffer.from([0x00]); // Version byte for legacy addresses

  // Step 2: Prepend version byte
  const data = Buffer.concat([versionByte, pkHashBin]);

  // Step 3: Append checksum
  const hash1 = sha256(data)
  const hash = sha256(hash1, 'hex')
  const checksum = Buffer.from(hash, 'hex').slice(0, 4);
  const dataWithChecksum = Buffer.concat([data, checksum]);

  // Step 5: Base58 encode the data with checksum
  const legacyAddress = binToBase58(dataWithChecksum);

  return legacyAddress;
}

export function pubkeyToAddress(pubkey, network='mainnet') {
  const pkhash = pubkeyToPkHash(pubkey)
  const legacyAddress = pkHashToLegacyAddress(pkhash)
  const decodedLegacyAddress = decodeBase58Address(legacyAddress)
  const prefix = network === 'mainnet' ? 'bitcoincash' : 'bchtest'
  return encodeCashAddress(prefix, 'p2pkh', decodedLegacyAddress.payload)
}

export function generateRandomWif() {
  return encodePrivateKeyWif(generatePrivateKey(), 'mainnet')
}

export function wifToPubkey(wif) {
  const privkey = decodePrivateKeyWif(wif)
  const compressed = secp256k1.derivePublicKeyCompressed(privkey.privateKey)
  if (typeof compressed !== 'string') return binToHex(compressed)
  const uncompressed = secp256k1.derivePublicKeyUncompressed(privkey.privateKey)
  if (typeof uncompressed !== 'string') return binToHex(uncompressed)
  return uncompressed
}

/**
 * @param {String} signatureB64 
 * @param {String} pubkeyHex 
 * @param {String} dataHex 
 */
export function verifyECDSASignature(signatureB64, pubkeyHex, dataHex) {
  const signature = base64ToBin(signatureB64)
  const pubkey = hexToBin(pubkeyHex)
  const message = hexToBin(dataHex)

  return secp256k1.verifySignatureCompact(signature, pubkey, message)
}

/**
 * @param {Object} utxo
 * @param {String} utxo.txid
 * @param {Number} utxo.vout
 * @param {Number | String} utxo.satoshis
 * @param {Object} [utxo.token]
 * @param {Number | String} utxo.token.amount
 * @param {String} utxo.token.category
 * @param {Object} [utxo.token.nft]
 * @param {'none' | 'mutable' | 'minting'} utxo.token.nft.capability
 * @param {String} utxo.token.nft.commitment
 * @param {String} [utxo.wif]
 * @param {String} [utxo.unlockingBytecode]
 * @param {String} [utxo.lockingBytecode]
 * @returns {import('cashscript').UtxoP2PKH | import('cashscript').Utxo}
 */
export function parseUtxo(utxo) {
  const result = {
    txid: utxo?.txid,
    vout: utxo?.vout,
    satoshis: BigInt(utxo?.satoshis),
    token: !utxo?.token ? undefined : {
      category: utxo?.token?.category,
      amount: BigInt(utxo?.token?.amount),
      nft: !utxo?.token?.nft ? undefined : {
        capability: utxo?.token?.nft?.capability,
        commitment: utxo?.token?.nft?.commitment,
      }
    },
  }

  if (utxo?.wif) {
    result.template = new SignatureTemplate(wif)
  } else if (utxo?.lockingBytecode && utxo?.unlockingBytecode) {
    result.template = templateFromUnlockingBytecode({
      lockingBytecode: utxo?.lockingBytecode,
      unlockingBytecode: utxo?.unlockingBytecode,
    })
  }

  return result
}

/**
 * @param {Object} output 
 * @param {String} output.to
 * @param {Number} output.amount
 * @param {Object} [output.token]
 * @param {Number | String} output.token.amount
 * @param {String} output.token.category
 * @param {Object} [output.token.nft]
 * @param {'none' | 'mutable' | 'minting'} output.token.nft.capability
 * @param {String} output.token.nft.commitment
 * @returns {import('cashscript').Output}
 */
export function parseCashscriptOutput(output) {
  return {
    to: isHex(output?.to) ? hexToBin(output?.to) : output?.to,
    amount: BigInt(output?.amount),
    token: !output?.token ? undefined : {
      category: output?.token?.category,
      amount: BigInt(output?.token?.amount),
      nft: !output?.token?.nft ? undefined : {
        capability: output?.token?.nft?.capability,
        commitment: output?.token?.nft?.commitment,
      }
    },
  }
}

/**
 * @param {import('cashscript').Utxo} utxo
 */
export function serializeUtxo(utxo) {
  return {
    txid: utxo?.txid,
    vout: utxo?.vout,
    satoshis: String(utxo?.satoshis),
    token: !utxo?.token ? undefined : {
      category: utxo?.token?.category,
      amount: String(utxo?.token?.amount),
      nft: !utxo?.token?.nft ? undefined : {
        capability: utxo?.token?.nft?.capability,
        commitment: utxo?.token?.nft?.commitment,
      }
    }
  }
}
