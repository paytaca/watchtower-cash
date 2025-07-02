import { getAnyhedgeBaseBytecode, calculateTotalFundingSatoshis, getContractDataOutputs } from './anyhedge.js'
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
  getRedemptionContractBaseBytecode,
  compileRedemptionContract,
  deposit,
  redeem,
  sweepRedemptionContract,
  transferRedemptionContractAssets,
  unlockRedemptionContractWithNft,
  consolidateRedemptionContract,
} from './redemption-contract.js'
import { generatePriceMessage, parsePriceMessage } from './price-oracle.js'
import { sweepUtxos, schnorrSign, signAuthKeyUtxo } from './transaction.js'
import { transferTreasuryFundsToRedemptionContract } from './rebalancing.js'

export default {
  getAnyhedgeBaseBytecode,
  calculateTotalFundingSatoshis,
  getContractDataOutputs,

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
  getRedemptionContractBaseBytecode,
  compileRedemptionContract,
  deposit,
  redeem,
  sweepRedemptionContract,
  transferRedemptionContractAssets,
  unlockRedemptionContractWithNft,
  consolidateRedemptionContract,

  parsePriceMessage,
  generatePriceMessage,

  sweepUtxos,
  schnorrSign,
  signAuthKeyUtxo,

  transferTreasuryFundsToRedemptionContract,
}
