import { AnyHedgeManager} from '@generalprotocols/anyhedge'

export const LIQUIDITY_FEE_NAME = 'Liquidity premium'

/**
 *
 * @typedef FundingProposal
 * @property {String} txHash - The transaction hash of the Outpoint (UTXO) being spent.
 * @property {Number} txIndex - The index of the Outpoint (UTXO) being spent.
 * @property {Number} txValue - The satoshis locked in the Outpoint (UTXO).
 * @property {String} scriptSig - The signature to provide to the Liquidity Provider so that the Contract can be funded.
 * @property {String} publicKey - The public key that corresponds to the signature. (TODO: unsure where to retrieve this)
 * @property {String[]} inputTxHashes - Array of transaction hashes that the outpoint depends upon.
 * 
 */

/**
 * 
 * @param {Object} contractData 
 * @param {'hedge' | 'long'} position - taker of hedge contract, who will take the liquidity provider fee
 * @param {Number} liquidityProviderFeeInSatoshis 
 * @returns 
 */
export function calculateFundingAmounts(contractData, position, liquidityProviderFeeInSatoshis=0) {
  const localContractMetadata = contractData.metadata
  const takerPayoutAddress = position === 'hedge'?
    localContractMetadata.hedgePayoutAddress : localContractMetadata.longPayoutAddress

  const makerInputSats = position === 'long' ? localContractMetadata.hedgeInputInSatoshis : localContractMetadata.longInputInSatoshis;

  const manager = new AnyHedgeManager()
  const totalRequiredFundingSatoshis = manager.calculateTotalRequiredFundingSatoshis(contractData)

  const takerTotalFeesAndPremiumsToDeduct = contractData.fees
    .reduce((total, fee) => {
      // If the fee is going to the taker's address, add it to the amount that must
      // be deducted from the total that taker should pay ..
      // must check the fee name to verify that it is really the liquidity premium
      if (fee.name === LIQUIDITY_FEE_NAME && fee.address === takerPayoutAddress) {
        return total += fee.satoshis;
      }

      // Return the previous total.
      return total;
    }, 0);

  const takerRequiredFundingSatoshis = totalRequiredFundingSatoshis - makerInputSats - takerTotalFeesAndPremiumsToDeduct + liquidityProviderFeeInSatoshis;

  // Calculate the amounts necessary to fund the contract.
  const contractAmount = {
    hedge: 0,
    long: 0,
  }
  
  if (position == 'hedge') {
    contractAmount.hedge = takerRequiredFundingSatoshis
    contractAmount.long = totalRequiredFundingSatoshis - takerRequiredFundingSatoshis
  } else if (position == 'long') {
    contractAmount.hedge = totalRequiredFundingSatoshis - takerRequiredFundingSatoshis
    contractAmount.long = takerRequiredFundingSatoshis
  }

  return contractAmount
}

/**
 * 
 * @typedef 
 * @param {Object} contractData 
 * @param {FundingProposal} fundingProposal1 
 * @param {FundingProposal} fundingProposal2 
 */
export async function completeFundingProposal(contractData, fundingProposal1, fundingProposal2) {
  const response = { success: false, error: '', fundingTxHex: ''}
  const manager = new AnyHedgeManager()
  const signedFundingProposal1 = {
    contractData: contractData,
    publicKey: fundingProposal1.publicKey,
    signature: fundingProposal1.scriptSig,
    utxo: {
      txid: fundingProposal1.txHash,
      vout: fundingProposal1.txIndex,
      satoshis: fundingProposal1.txValue,
    }
  }

  const signedFundingProposal2 = {
    contractData: contractData,
    publicKey: fundingProposal2.publicKey,
    signature: fundingProposal2.scriptSig,
    utxo: {
      txid: fundingProposal2.txHash,
      vout: fundingProposal2.txIndex,
      satoshis: fundingProposal2.txValue,
    }
  }

  try{  
    const fundingTxHex = await manager.completeFundingProposal(signedFundingProposal1, signedFundingProposal2)
    response.success = true
    response.fundingTxHex = fundingTxHex
  } catch(error) {
    response.success = false
    response.error = error?.message || 'Error completing funding proposal'
  }
  return response
}
