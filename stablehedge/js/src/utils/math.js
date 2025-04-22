export function round(value, decimals=8, floor=true) {
  const multiplier = 10 ** decimals
  const func = floor ? Math.floor : Math.round
  return func(value * multiplier) / multiplier
}

/**
 * Converts an integer to hexadecimal in little-endian notation
 * (e.g. 64**2, big endian => `0x1000`, little endian => `0x0010`)
 * @param {Number | BigInt} num 
 * @param {Number} bytelength 
 * @returns {String}
 */
export function intToHexString(num=20, bytelength=20) {
  const hexString = num.toString(16).padStart(bytelength * 2, '0')
  return reverseHex(hexString)
}

export function reverseHex(hex = '') {
  if (hex.length % 2 !== 0) {
    throw new Error("Hex string length must be even");
  }
  return hex.match(/../g).reverse().join('');
}

/**
 * 
 * @param {Number[] | BigInt[]} numbers 
 * @param {Number} elementBytes 
 */
export function numbersToCumulativeHexString(numbers, elementBytes=4) {
  let subtotal = 0n
  const cumulativeSats = numbers.map(num => {
    subtotal += BigInt(num);
    return subtotal
  })

  const hexCumulatives = cumulativeSats.map(sats => intToHexString(sats, elementBytes))
  return hexCumulatives.reduce((substr, satsHex) => substr + satsHex, '')
}
