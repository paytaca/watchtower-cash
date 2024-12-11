export function round(value, decimals=8, floor=true) {
  const multiplier = 10 ** decimals
  const func = floor ? Math.floor : Math.round
  return func(value * multiplier) / multiplier
}

/**
 * Converts an integer to hexadecimal in little-endian notation
 * (e.g. 64**2, big endian => `0x1000`, little endian => `0x0010`)
 * @param {Number} num 
 * @param {Number} bytelength 
 * @returns {String}
 */
export function intToHexString(num=20, bytelength=20) {
  let numHexBase = num.toString(16)
  if (numHexBase.length % 2 != 0) numHexBase = '0' + numHexBase
  let numBytes = Buffer.from(numHexBase, 'hex')
  if (bytelength !== numBytes.length) {
    numBytes = Buffer.concat([
      Buffer.from(new Array(bytelength - numBytes.length).fill(0)),
      numBytes,
    ])
  }
  numBytes.reverse()
  return numBytes.toString('hex')
}
