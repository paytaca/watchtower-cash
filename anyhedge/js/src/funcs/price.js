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
 * @property {String} oracleRelayPort
 * 
 * @typedef {Object} PriceRequestParams
 * @property {Number|undefined} minDataSequence 
 * @property {Number|undefined} maxDataSequence 
 * @property {Number|undefined} minMessageTimestamp 
 * @property {Number|undefined} maxMessageTimestamp 
 * @property {Number|undefined} minMessageSequence 
 * @property {Number|undefined} minMessageSequence 
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
 * @property {String} oraclePubKey - 33-bit hex string public key of the oracle
 * 
 */


/**
 * @param {PriceMessageConfig|undefined} config
 * @returns {Promise<OraclePriceMessage>} oracle price message
 */
export async function getPriceMessage(config) {
	const _conf = {
		publicKey: config?.oraclePubKey || ORACLE_PUBLIC_KEY,
		relay: config?.oracleRelay || ORACLE_RELAY,
		port: config?.oracleRelayPort || ORACLE_RELAY_PORT,
	}
	const searchRequest = {
		publicKey: _conf.publicKey,
		minDataSequence: 1,
		count: 1,
	};
	const requestedMessages = await OracleNetwork.request(searchRequest, _conf.relay, _conf.port);
	const { message, signature, publicKey } = requestedMessages[0];

	// const message = '5003d6623f100200ee0f0200c32e0000'
	// const signature = '405e46f66e9d77582849e3c68bfdd05af42324b32dda1f537cc9b205c4bad73a6d7a45cf720e79efd1e899e92face2c9867cc08984a7e1705eeddf7fe0fd98b1'
	// const publicKey = '02d3c1de9d4bc77d6c3608cbe44d10138c7488e592dc2b1e10a6cf0e92c2ecb047'
	return { message, signature, publicKey }
}

/**
 * 
 * @param {PriceMessageConfig|undefined} config
 * @returns {Promise<{priceData: PriceMessageData, msgData: OraclePriceMessage}>}
 */
export async function getPrice(config) {
	const msgData = await getPriceMessage(config)
	let { message, signature, publicKey } = msgData
	const validMessageSignature = await OracleData.verifyMessageSignature(
		hexToBin(message),
		hexToBin(signature),
		hexToBin(publicKey)
	);

	if (!validMessageSignature) {
		throw (new Error('Could not get starting conditions due to the oracle relay providing an invalid signature for the message.'));
	}
	const priceData = await OracleData.parsePriceMessage(hexToBin(message))
	priceData.oraclePubKey = msgData.publicKey
	return { priceData, msgData }
}

/**
 * 
 * @param {PriceMessageConfig|undefined} config
 * @returns {Promise<PriceMessageData>}
 */
export async function getPriceData(config) {
	const price = await getPrice(config)
	return price.priceData
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
	const _searchRequest = Object.assign({ publicKey: _conf.publicKey }, requestParams)
	const searchRequest = Object.assign({}, _searchRequest)
	if (!searchRequest.count) searchRequest.count = 1
	const requestedMessages = await OracleNetwork.request(searchRequest, _conf.relay, _conf.port);

	if (!Array.isArray(requestedMessages)) {
		response.success = false
		response.error = requestedMessages
		return response
	}

	const parsedMessages = await Promise.all(
		requestedMessages.map(async (priceMessage) => {
			const { message, signature, publicKey } = priceMessage
			const validMessageSignature = await OracleData.verifyMessageSignature(
				hexToBin(message),
				hexToBin(signature),
				hexToBin(publicKey)
			);

			if (!validMessageSignature) {
				return null
			}

			const priceData = await OracleData.parsePriceMessage(hexToBin(message))
			return { priceMessage, priceData }
		})
	)

	response.results = parsedMessages
	response.success = true
	return response
}
