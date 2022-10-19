import axios from 'axios'

/**
 * @typedef HedgePositionOffer
 * @property {Number} satoshis
 * @property {Number} durationSeconds
 * @property {Number} lowLiquidationMultiplier
 * @property {Number} highLiquidationMultiplier
 * @property {String} hedgeAddress
 * @property {String} hedgePubkey
 * 
 * @typedef FundingProposal
 * @property {String} txHash - The transaction hash of the Outpoint (UTXO) being spent.
 * @property {Number} txIndex - The index of the Outpoint (UTXO) being spent.
 * @property {Number} txValue - The satoshis locked in the Outpoint (UTXO).
 * @property {String} scriptSig - The signature to provide to the Liquidity Provider so that the Contract can be funded.
 * @property {String} publicKey - The public key that corresponds to the signature. (TODO: unsure where to retrieve this)
 * @property {String[]} inputTxHashes - Array of transaction hashes that the outpoint depends upon.
 */

const BASE_URL = process.env.ANYHEDGE_LP_BASE_URL || 'https://staging-liquidity.anyhedge.com'

const backend = axios.create({
  baseURL: BASE_URL,
})

/**
 * 
 * @param {Object} contractData 
 * @param {FundingProposal} fundingProposal 
 * @param {Number} oracleMessageSequence 
 * @param {'hedge' | 'long'} position
 */
export async function fundHedgePosition(contractData, fundingProposal, oracleMessageSequence, position='hedge') {
  const response = { success: false, fundingTransactionHash: '', error: '' }
  const fundContractData = {
    contractAddress: contractData.address,
    outpointTransactionHash: fundingProposal.txHash,
    outpointIndex: fundingProposal.txIndex,
    satoshis: fundingProposal.txValue,
    signature: fundingProposal.scriptSig,
    publicKey: fundingProposal.publicKey,
    takerSide: position,
    dependencyTransactions: fundingProposal.inputTxHashes,
    oracleMessageSequence: oracleMessageSequence,
  }

  // const input = contractData?.metadata?.hedgeInputSats
  // const fees = contractData?.fee?.satoshis
  // const expectedFundingSats = input + fees
  // if (fundingProposal.txValue !== expectedFundingSats) {
  //   response.success = false
  //   response.error = `Funding proposal satoshis must be ${input} + ${fees}, got ${fundingProposal.txValue}`
  //   return response
  // }

  try {
    const fundContractResponse = await backend.post('/api/v1/fundContract', fundContractData)
    // https://gitlab.com/GeneralProtocols/anyhedge/library/-/blob/development/lib/interfaces/liquidity-provider.ts#L147
    response.fundingTransactionHash = fundContractResponse.data.fundingTransactionHash
    response.success = true
  } catch(error) {
    response.success = false
    if (Array.isArray(error?.response?.data?.errors)) {
      response.errors = error.response.data.errors
      response.error = response.errors?.[0]
    } else if (error?.message) {
      response.error = error?.message
    }
  }

  return response
}
