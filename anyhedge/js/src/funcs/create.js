import { getPriceMessages } from './price.js'
import { AnyHedgeManager } from '@generalprotocols/anyhedge'

/**
 * 
 * @param {Object} intent - Contract creation parameters
 * @param {Number} intent.amount - Amount of BCH to hedge
 * @param {Number} intent.lowPriceMult - The USD/BCH price drop percentage to trigger liquidation
 * @param {Number} intent.highPriceMult - The USD/BCH price increase percentage to trigger liquidation
 * @param {Number} intent.duration - The number of seconds from the starting time of the hedge position
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
    const priceData = priceMessagesResponse?.results?.[0]?.priceData
    if (!priceData) throw 'Unable to retrieve price data'

    const nominalUnits = intent.amount * priceData.priceValue // BCH * (UScents / BCH)

    if (nominalUnits < 10 || nominalUnits > 1 * 10**9) throw 'Amount is outside allowed range'  

    if (intent.lowPriceMult < 0 || intent.lowPriceMult >= 1) throw 'Lowest price drop range invalid'
    if (intent.highPriceMult <= 1 || intent.highPriceMult > 10) throw 'Largest price rise range invalid'

    const contractCreationParameters = {
      nominalUnits: nominalUnits,
      duration: intent.duration,
      startPrice: priceData.priceValue,
      startTimestamp: priceData.messageTimestamp,
      oraclePublicKey: priceData.oraclePubKey,
      // enableMutualRedemption: true,
      highLiquidationPriceMultiplier: intent.highPriceMult,
      lowLiquidationPriceMultiplier: intent.lowPriceMult,
      hedgePublicKey: pubkeys.hedgePubkey,
      longPublicKey: pubkeys.shortPubkey,
      hedgeAddress: pubkeys.hedgeAddress,
      longAddress: pubkeys.shortAddress,
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
 * @param {Number} contractCreationParameters.nominalUnits - US cents
 * @param {Number} contractCreationParameters.duration - duration in seconds
 * @param {Number} contractCreationParameters.startPrice - US cents per BCH
 * @param {Number} contractCreationParameters.startTimestamp
 * @param {String} contractCreationParameters.oraclePublicKey
 * @param {Number} contractCreationParameters.highLiquidationPriceMultiplier
 * @param {Number} contractCreationParameters.lowLiquidationPriceMultiplier
 * @param {String} contractCreationParameters.hedgePublicKey
 * @param {String} contractCreationParameters.longPublicKey
 * @param {String} contractCreationParameters.hedgeAddress
 * @param {String} contractCreationParameters.longAddress
 * @returns 
 */
export async function compileContract(contractCreationParameters) {
  const manager = new AnyHedgeManager();
  return await manager.createContract(contractCreationParameters);
}
