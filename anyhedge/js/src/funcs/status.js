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
  const opts = {
    params: { contractAddress: contractAddress, publicKey: pubkey, signature: signature },
    headers: {}
  }
  if (settlementService.authenticationToken) opts.headers.Authorization = settlementService.authenticationToken
  let url = new URL(`${settlementService.scheme}://${settlementService.domain}:${settlementService.port}/api/v1/contractStatus`)

  // NOTE: handling old & new implementation since settlement service might be using the old one
  //       remove handling old one after upgrade is stable
  const { data } = await axios.get(String(url), opts)
    .catch(error => {
      if (error?.response?.status != 404) return Promise.reject(error)
      url.pathname = '/status'
      return axios.get(String(url), opts)
    })
  return data
}
