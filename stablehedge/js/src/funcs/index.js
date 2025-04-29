import { getAnyhedgeBaseBytecode, calculateTotalFundingSatoshis } from './anyhedge.js'
import {
  compileTreasuryContract,
  getTreasuryContractArtifact,
  sweepTreasuryContract,
  unlockTreasuryContractWithMultiSig,
  unlockTreasuryContractWithNft,
  constructTreasuryContractTx,
  verifyTreasuryContractMultisigTx,
  getMultisigTxUnlockingScripts,
  signMutliSigTx,
  spendToAnyhedgeContract,
  consolidateTreasuryContract,
 } from './treasury-contract.js'
import {
  getRedemptionContractArtifact,
  compileRedemptionContract,
  deposit,
  redeem,
  sweepRedemptionContract,
  transferRedemptionContractAssets,
  unlockRedemptionContractWithNft,
} from './redemption-contract.js'
import { generatePriceMessage, parsePriceMessage } from './price-oracle.js'
import { sweepUtxos, schnorrSign, signAuthKeyUtxo } from './transaction.js'
import { transferTreasuryFundsToRedemptionContract } from './rebalancing.js'

export default {
  getAnyhedgeBaseBytecode,
  calculateTotalFundingSatoshis,

  getTreasuryContractArtifact,
  compileTreasuryContract,
  sweepTreasuryContract,
  unlockTreasuryContractWithMultiSig,
  unlockTreasuryContractWithNft,
  constructTreasuryContractTx,
  verifyTreasuryContractMultisigTx,
  getMultisigTxUnlockingScripts,
  signMutliSigTx,
  spendToAnyhedgeContract,
  consolidateTreasuryContract,

  getRedemptionContractArtifact,
  compileRedemptionContract,
  deposit,
  redeem,
  sweepRedemptionContract,
  transferRedemptionContractAssets,
  unlockRedemptionContractWithNft,

  parsePriceMessage,
  generatePriceMessage,

  sweepUtxos,
  schnorrSign,
  signAuthKeyUtxo,

  transferTreasuryFundsToRedemptionContract,
}
