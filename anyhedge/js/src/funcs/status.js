import axios from 'axios'

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
