import BCHJS from "@psf/bch-js"

const bchjs = new BCHJS()


export function reverseHex (hexString) {
  const bytes = Buffer.from(hexString, 'hex')
  bytes.reverse()
  return bytes.toString('hex')
}

export function toBytes32 (val, encoding = "utf8", toString = false) {
  let bytes32 = bchjs.Crypto.hash256(Buffer.from(val, encoding))
  if (toString) bytes32 = bytes32.toString("hex")
  return bytes32
}