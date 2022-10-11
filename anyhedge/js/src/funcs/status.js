import axios from 'axios'
import { AnyHedgeManager } from "@generalprotocols/anyhedge";

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
    const manager = new AnyHedgeManager({
      serviceScheme: settlementService.scheme,
      serviceDomain: settlementService.domain,
      servicePort: settlementService.port,
    })
    settlementService.authenticationToken = await manager.requestAuthenticationToken('Paytaca')
  }

  const { data } = await axios.get(
    `${settlementService.scheme}://${settlementService.domain}:${settlementService.port}/status`,
    {
      params: {
        contractAddress: contractAddress,
        publicKey: pubkey,
        signature: signature,
      },
      headers: {
        Authorization: settlementService.authenticationToken,
      }
    }
  )
  return data
}
