import { getPriceMessages } from './price.js'
import { AnyHedgeManager } from '@generalprotocols/anyhedge'

/**
 * 
 * @param {Object} intent - Contract creation parameters
 * @param {Number} intent.amount - Amount of BCH to hedge
 * @param {Number} intent.lowPriceMult - The USD/BCH price drop percentage to trigger liquidation
 * @param {Number} intent.highPriceMult - The USD/BCH price increase percentage to trigger liquidation
 * @param {Number} intent.duration - The number of seconds from the starting time of the hedge position
 * @param {'hedge' | 'long'} intent.takerSide - Taker of contract
 * @param {Object} pubkeys - Necessary credentials for hedge and short
 * @param {String} pubkeys.hedgeAddress - Destination address of hedger's funds on maturity/liquidation
 * @param {String} pubkeys.hedgePubkey - Public key of hedger
 * @param {String} pubkeys.shortAddress - Destination address of counterparty's funds on maturity/liquidation
 * @param {String} pubkeys.shortPubkey - Public key of counterparty
 * @param {PriceMessageConfig | undefined } priceMessageConfig
 * @param {PriceRequestParams | undefined } priceMessageRequestParams
 */
export async function create(intent, pubkeys, priceMessageConfig, priceMessageRequestParams) {
  try {
    const priceMessagesResponse = await getPriceMessages(priceMessageConfig, priceMessageRequestParams)
    const { priceData, priceMessage } = priceMessagesResponse?.results?.[0]
    if (!priceData) throw 'Unable to retrieve price data'

    const nominalUnits = intent.amount * priceData.priceValue // BCH * (UScents / BCH)

    if (nominalUnits < 10 || nominalUnits > 1 * 10**9) throw 'Amount is outside allowed range'  

    if (intent.lowPriceMult < 0 || intent.lowPriceMult >= 1) throw 'Lowest price drop range invalid'
    if (intent.highPriceMult <= 1 || intent.highPriceMult > 10) throw 'Largest price rise range invalid'

    const contractCreationParameters = {
      takerSide: intent.takerSide,
      makerSide: intent.takerSide === 'hedge' ? 'long' : 'hedge',
      nominalUnits: nominalUnits,
      oraclePublicKey: priceMessage.publicKey,
      startingOracleMessage: priceMessage.message,
      startingOracleSignature: priceMessage.signature,
      maturityTimestamp: priceData.messageTimestamp + intent.duration,
      lowLiquidationPriceMultiplier: intent.lowPriceMult,
      highLiquidationPriceMultiplier: intent.highPriceMult,
      hedgePayoutAddress: pubkeys.hedgeAddress,
      longPayoutAddress: pubkeys.shortAddress,
      hedgeMutualRedeemPublicKey: pubkeys.hedgePubkey,
      longMutualRedeemPublicKey: pubkeys.shortPubkey,
      enableMutualRedemption: 1,
    }

    const resp = await compileContract(contractCreationParameters)
    return { success: true, contractData: resp }
  } catch(err) {
    console.error(err)
    return { success: false, error: err }
  }
}

/**
 * 
 * @param {Object} contractCreationParameters 
 * @param {'hedge' | 'long'} contractCreationParameters.takerSide
 * @param {'hedge' | 'long'} contractCreationParameters.makerSide
 * @param {Number} contractCreationParameters.nominalUnits - US cents
 * @param {String} contractCreationParameters.oraclePublicKey
 * @param {String} contractCreationParameters.startingOracleMessage
 * @param {String} contractCreationParameters.startingOracleSignature
 * @param {Number} contractCreationParameters.maturityTimestamp
 * @param {Number} contractCreationParameters.highLiquidationPriceMultiplier
 * @param {Number} contractCreationParameters.lowLiquidationPriceMultiplier
 * @param {String} contractCreationParameters.hedgeMutualRedeemPublicKey
 * @param {String} contractCreationParameters.longMutualRedeemPublicKey
 * @param {String} contractCreationParameters.hedgePayoutAddress
 * @param {String} contractCreationParameters.longPayoutAddress
 * @param {0 | 1} contractCreationParameters.enableMutualRedemption
 * @param {{address: String, satoshis: Number}[]} fees
 * @param {{txHash:String,fundingOutput:Number,fundingSatoshis:Number}[]} fundings
 * @returns 
 */
export async function compileContract(contractCreationParameters, fees, fundings) {
  const manager = new AnyHedgeManager();
  const contractData = await manager.createContract(contractCreationParameters);
  if (Array.isArray(fees)) {
    contractData.fees = fees
      .map(fee => Object({
        name: fee?.name || '',
        description: fee?.description || '',
        address: fee?.address,
        satoshis: fee?.satoshis,
      }))
      .filter(fee => fee?.address && fee?.satoshis)
  }

  if (Array.isArray(fundings)) {
    contractData.fundings = fundings
      .filter(funding => funding?.txHash && funding?.fundingSatoshis)
      .map(funding => Object({
        fundingTransactionHash: funding.txHash,
        fundingOutputIndex: funding.fundingOutput,
        fundingSatoshis: funding.fundingSatoshis,
      }))
  }
  return contractData
}
