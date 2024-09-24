import { decodePriceMessage, generatePriceMessage, verifyPriceMessage } from "../utils/price-oracle.js";

export {
  generatePriceMessage,
}

/**
 * @param {Object} opts 
 * @param {String} opts.priceMessage
 * @param {String} [opts.publicKey]
 * @param {String} [opts.signature]
 */
export function parsePriceMessage(opts) {
  if (opts?.publicKey && opts?.signature) {
    if (!verifyPriceMessage(opts?.priceMessage, opts?.signature, opts?.publicKey)) {
      return { success: false, error: 'Invalid signature'}
    }
  }
  const priceData = decodePriceMessage(opts?.priceMessage)
  if (typeof priceData === 'string') return { success: false, error: priceData }
  return { success:true, priceData: priceData }
}
