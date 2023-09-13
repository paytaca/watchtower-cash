import BCHJS from '@psf/bch-js'
const bchjs = new BCHJS()


export function toBytes20 ({ val, encoding = "utf8", toString = false }) {
  let bytes20 = bchjs.Crypto.hash160(Buffer.from(val, encoding))
  if (toString) bytes20 = bytes20.toString("hex")
  return bytes20
}

export function pubkeyToCashAddress ({ pubkey }) {
  const ecpair = bchjs.ECPair.fromPublicKey(Buffer.from(pubkey, 'hex'))
  return bchjs.ECPair.toCashAddress(ecpair)
}
