import axios from 'axios'
import { castContractDataV1toContractDataV2, decodeExtendedJson } from '@generalprotocols/anyhedge'

import { IncorrectWIFError } from '@generalprotocols/anyhedge'
import { decodePrivateKeyWif, binToHex, secp256k1, utf8ToBin, sha256 } from '@bitauth/libauth';

/**
 * 
 * @param {String} contractAddress 
 * @param {String} pubkey 
 * @param {String} signature 
 * @param {Object} settlementService 
 * @param {String} settlementService.scheme 
 * @param {String} settlementService.domain 
 * @param {String} settlementService.port 
 * @param {String} settlementService.authenticationToken 
 */
export async function getContractStatus(contractAddress, pubkey, signature, settlementService) {
  if (!settlementService.authenticationToken) {
    settlementService.authenticationToken = process.env.ANYHEDGE_SETTLEMENT_SERVICE_AUTH_TOKEN
  }
  const opts = {
    params: { contractAddress: contractAddress, publicKey: pubkey, signature: signature },
    headers: {},
    transformResponse: [
      function(data, /* headers */) {
        try {
          return decodeExtendedJson(data)
        } catch {
          return data
        }
      }
    ]
  }
  if (settlementService.authenticationToken) opts.headers.Authorization = settlementService.authenticationToken

  let path = '/api/v2/contractStatus'
  if (settlementService?.domain?.includes?.('staging-')) path = '/api/v1/contractStatus'

  let url = new URL(`${settlementService.scheme}://${settlementService.domain}:${settlementService.port}${path}`)

  // NOTE: handling old & new implementation since settlement service might be using the old one
  //       remove handling old one after upgrade is stable
  let { data } = await axios.get(String(url), opts)
    .catch(error => {
      if (error?.response?.status != 404) return Promise.reject(error)
      url.pathname = '/status'
      return axios.get(String(url), opts)
    })

  if ([data?.metadata?.takerSide, data?.metadata?.makerSide].includes('hedge')) {
    data = castContractDataV1toContractDataV2(data)
  }
  return data
}


/**
 * Generate signature and pubkey needed to access the contract in a settlement service
 * @see {@link https://gitlab.com/GeneralProtocols/anyhedge/library/-/blob/v0.14.2/lib/anyhedge.ts#L399} for reference
 * 
 * @param {String} contractAddress 
 * @param {String} privateKeyWIF 
 */
 export async function getContractAccessKeys(contractAddress, privateKeyWIF) {
    const privateKeyBin = decodePrivateKeyWif(privateKeyWIF).privateKey
	if(typeof privateKeyBin === 'string') throw(new IncorrectWIFError(privateKeyWIF))

    const publicKeyBin = secp256k1.derivePublicKeyCompressed(privateKeyBin)
    if(typeof publicKeyBin === 'string') throw new Error(publicKeyBin)
    const publicKey = binToHex(publicKeyBin)

    const messageHash = await sha256.hash(utf8ToBin(contractAddress))
    const signatureBin = secp256k1.signMessageHashSchnorr(privateKeyBin, messageHash);
    if(typeof signatureBin === 'string') throw new Error(signatureBin)
    const signature = binToHex(signatureBin);

    return { publicKey, signature }
}
