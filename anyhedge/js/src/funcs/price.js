import { OracleNetwork, OracleData } from '@generalprotocols/price-oracle'
import { hexToBin } from '@bitauth/libauth'

const ORACLE_PUBLIC_KEY = '02d3c1de9d4bc77d6c3608cbe44d10138c7488e592dc2b1e10a6cf0e92c2ecb047'
const ORACLE_RELAY = 'staging-oracles.generalprotocols.com'
const ORACLE_RELAY_PORT = 7083

/**
 * 
 * @typedef {Object} PriceMessageConfig
 * @property {String} oraclePubKey
 * @property {String} oracleRelay
 * @property {Number} oracleRelayPort
 * 
 * @typedef {Object} PriceRequestParams
 * @property {Number|undefined} minDataSequence 
 * @property {Number|undefined} maxDataSequence 
 * @property {Number|undefined} minMessageTimestamp 
 * @property {Number|undefined} maxMessageTimestamp 
 * @property {Number|undefined} minMessageSequence 
 * @property {Number|undefined} maxMessageSequence 
 * @property {Number|undefined} count 
 * 
 * @typedef {Object} OraclePriceMessage
 * @property {String} message - 16-bit hex string containing data of price message
 * @property {String} signature - 64-bit hex string signature
 * @property {String} publicKey - 33-bit hex string public key of the oracle
 * 
 * @typedef {Object} PriceMessageData
 * @property {Number} messageTimestamp - Unix timestamp in UTC and seconds for the moment the oracle produced this message.
 * @property {Number} messageSequence - Sequence number for this price message relative to all of this oracle's messages.
 * @property {Number} priceSequence - Sequence number for this price message relative to all of this oracle's price messages.
 * @property {Number} priceValue - Price of the asset. e.g. 'US cents per BCH'(USCents/BCH)
 * @property {String} [oraclePubKey] - 33-bit hex string public key of the oracle
 * 
 */

/**
 * 
 * @param {String} message 
 * @param {String} [publicKey]
 * @param {String} [signature]
 */
export async function parseOracleMessage(message, publicKey, signature) {
	const response = { success: false, priceData: {}, error: null }
	try {
		if (publicKey && signature) {
			const validMessageSignature = await OracleData.verifyMessageSignature(hexToBin(message), hexToBin(signature), hexToBin(publicKey));
			if (!validMessageSignature) throw new Error('Oracle message invalid')
		}
		response.priceData = await OracleData.parsePriceMessage(hexToBin(message))
		if (publicKey) response.priceData.oraclePubKey = publicKey
		response.success = true
		return response
	} catch(error) {
		if (typeof error === 'string') response.error = error
		else if (error?.message) response.error = error.message
		response.success = false
	}
	return response
}

/**
 * 
 * @param {PriceMessageConfig|undefined} config 
 * @param {PriceRequestParams|undefined} requestParams 
 * @returns {{success:Boolean, error:String, results: { priceMessage: OraclePriceMessage, priceData: PriceMessageData }[]}}
 */
export async function getPriceMessages(config, requestParams) {
	const response = { success: false, results: [], error: '' }

	const _conf = {
		publicKey: config?.oraclePubKey || ORACLE_PUBLIC_KEY,
		relay: config?.oracleRelay || ORACLE_RELAY,
		port: config?.oracleRelayPort || ORACLE_RELAY_PORT,
	}

	const defaultSearchRequest = { publicKey: _conf.publicKey, count: 1, minDataSequence: 1 }
	const searchRequest = Object.assign({}, defaultSearchRequest, requestParams)
	const requestedMessages = await OracleNetwork.request(searchRequest, _conf.relay, _conf.port);

	if (!Array.isArray(requestedMessages)) {
		response.success = false
		response.error = requestedMessages
		return response
	}

	const parsedMessages = await Promise.all(
		requestedMessages.map(async (priceMessage) => {
			const { message, signature, publicKey } = priceMessage
			const parseOracleMessageResponse = await parseOracleMessage(message, publicKey, signature)
			if (!parseOracleMessageResponse.success) return parseOracleMessageResponse.error
			const priceData = parseOracleMessageResponse.priceData
			return { priceMessage, priceData }
		})
	)

	response.results = parsedMessages
	response.success = true
	return response
}
