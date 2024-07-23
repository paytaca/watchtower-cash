
export function reverseHex (hexString) {
  const bytes = Buffer.from(hexString, 'hex')
  bytes.reverse()
  return bytes.toString('hex')
}