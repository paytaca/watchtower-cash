import { castBigIntSafe, parseContractCreationParamsV2, transformContractCreationParamsV2toV1 } from '../utils.js'
import { getPriceMessages, parseOracleMessage } from './price.js'
import { AnyHedgeManager, castContractDataV1toContractDataV2 } from '@generalprotocols/anyhedge'
import { AnyHedgeArtifacts } from '@generalprotocols/anyhedge-contracts';
import { AnyHedgeManager as AnyHedgeManagerOld } from '@generalprotocols/anyhedge-old';


/**
 * 
 * @param {Object} intent - Contract creation parameters
 * @param {Number} intent.amount - Amount of BCH to hedge
 * @param {Number} intent.lowPriceMult - The USD/BCH price drop percentage to trigger liquidation
 * @param {Number} intent.highPriceMult - The USD/BCH price increase percentage to trigger liquidation
 * @param {Number} intent.duration - The number of seconds from the starting time of the hedge position
 * @param {Boolean} intent.isSimpleHedge - A simple hedge or a short position
 * @param {'short' | 'long'} intent.takerSide - Taker of contract
 * @param {Object} pubkeys - Necessary credentials for hedge and short
 * @param {String} pubkeys.longAddress - Destination address of hedger's funds on maturity/liquidation
 * @param {String} pubkeys.longPubkey - Public key of hedger
 * @param {String} pubkeys.shortAddress - Destination address of counterparty's funds on maturity/liquidation
 * @param {String} pubkeys.shortPubkey - Public key of counterparty
 * @param {OraclePriceMessage} [startingOracleMessage]
 * @param {PriceMessageConfig | undefined } priceMessageConfig
 * @param {PriceRequestParams | undefined } priceMessageRequestParams
 */
export async function create(intent, pubkeys, startingOracleMessage, priceMessageConfig, priceMessageRequestParams) {
  try {
    let startingPriceMessage
    if (startingOracleMessage?.publicKey &&
      startingOracleMessage?.message &&
      startingOracleMessage?.signature
    ) {
      const parsedPriceDataResponse = await parseOracleMessage(startingOracleMessage?.message)
      startingPriceMessage = {
        priceMessage: {
          publicKey: startingOracleMessage?.publicKey,
          message: startingOracleMessage?.message,
          signature: startingOracleMessage?.signature,
        },
        priceData: parsedPriceDataResponse.priceData,
      }
    }
    if (!startingPriceMessage) {
      try {
        const priceMessagesResponse = await getPriceMessages(priceMessageConfig, priceMessageRequestParams)
        startingPriceMessage = priceMessagesResponse?.results?.[0]
      } catch {}
    }

    if (!startingPriceMessage) throw 'Unable to retrieve price data'
    const { priceData, priceMessage } = startingPriceMessage
    if (!priceData) throw 'Unable to retrieve price data'

    const nominalUnits = intent.amount * priceData.priceValue // BCH * (UScents / BCH)

    if (nominalUnits < 10 || nominalUnits > 1 * 10**9) throw 'Amount is outside allowed range'  

    if (intent.lowPriceMult < 0 || intent.lowPriceMult >= 1) throw 'Lowest price drop range invalid'
    if (intent.highPriceMult <= 1 || intent.highPriceMult > 10) throw 'Largest price rise range invalid'

    const contractCreationParameters = {
      takerSide: intent.takerSide,
      makerSide: intent.takerSide === 'short' ? 'long' : 'short',
      nominalUnits: nominalUnits,
      oraclePublicKey: priceMessage.publicKey,
      startingOracleMessage: priceMessage.message,
      startingOracleSignature: priceMessage.signature,
      maturityTimestamp: castBigIntSafe(priceData.messageTimestamp + intent.duration),
      lowLiquidationPriceMultiplier: intent.lowPriceMult,
      highLiquidationPriceMultiplier: intent.highPriceMult,
      shortPayoutAddress: pubkeys.shortAddress,
      longPayoutAddress: pubkeys.longAddress,
      shortMutualRedeemPublicKey: pubkeys.shortPubkey,
      longMutualRedeemPublicKey: pubkeys.longPubkey,
      enableMutualRedemption: 1n,
      isSimpleHedge: intent.isSimpleHedge ? 1n : 0n,
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
 * @param {'short' | 'long'} contractCreationParameters.takerSide
 * @param {'short' | 'long'} contractCreationParameters.makerSide
 * @param {Number} contractCreationParameters.nominalUnits - US cents
 * @param {String} contractCreationParameters.oraclePublicKey
 * @param {String} contractCreationParameters.startingOracleMessage
 * @param {String} contractCreationParameters.startingOracleSignature
 * @param {Number} contractCreationParameters.maturityTimestamp
 * @param {Number} contractCreationParameters.highLiquidationPriceMultiplier
 * @param {Number} contractCreationParameters.lowLiquidationPriceMultiplier
 * @param {String} contractCreationParameters.shortMutualRedeemPublicKey
 * @param {String} contractCreationParameters.longMutualRedeemPublicKey
 * @param {String} contractCreationParameters.shortPayoutAddress
 * @param {String} contractCreationParameters.longPayoutAddress
 * @param {0 | 1} contractCreationParameters.enableMutualRedemption
 * @param {0 | 1} contractCreationParameters.isSimpleHedge
 * @param {{address: String, satoshis: Number}[]} fees
 * @param {{txHash:String,fundingOutput:Number,fundingSatoshis:Number}[]} fundings
 * @param {Object} opts
 * @param {String} [opts.contractVersion]
 * @returns 
 */
export async function compileContract(contractCreationParameters, fees, fundings, opts) {
  let contractData
  const contractVersion = opts?.contractVersion
  if (contractVersion && !AnyHedgeArtifacts[contractVersion]) {
    const contractCreationParametersV1 = transformContractCreationParamsV2toV1(contractCreationParameters)
    const managerOld = new AnyHedgeManagerOld({ contractVersion })
    contractData = await managerOld.createContract(contractCreationParametersV1)
    contractData = castContractDataV1toContractDataV2(contractData)
  } else {
    
    const contractCreationParametersV2 = parseContractCreationParamsV2(contractCreationParameters);
    const manager = new AnyHedgeManager({ contractVersion });
    contractData = await manager.createContract(contractCreationParametersV2);
  }

  if (Array.isArray(fees)) {
    contractData.fees = fees
      .map(fee => Object({
        name: fee?.name || '',
        description: fee?.description || '',
        address: fee?.address,
        satoshis: castBigIntSafe(fee?.satoshis),
      }))
      .filter(fee => fee?.address && fee?.satoshis)
  }

  if (Array.isArray(fundings)) {
    contractData.fundings = fundings
      .filter(funding => funding?.txHash && funding?.fundingSatoshis)
      .map(funding => Object({
        fundingTransactionHash: funding.txHash,
        fundingOutputIndex: castBigIntSafe(funding.fundingOutput),
        fundingSatoshis: castBigIntSafe(funding.fundingSatoshis),
      }))
  }
  return contractData
}
