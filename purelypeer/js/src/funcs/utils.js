import BCHJS from '@psf/bch-js'
const bchjs = new BCHJS()


export function toBytes20 (val, encoding = "utf8", toString = false) {
  let bytes20 = bchjs.Crypto.hash160(Buffer.from(val, encoding))
  if (toString) bytes20 = bytes20.toString("hex")
  return bytes20
}

export function cashAddrToPubkey ({ address, hash = false, toString = false }) {
  const legacyAddress = bchjs.Address.toLegacyAddress(address)
  const pubkey = bchjs.BitcoinCash.decodeBase58Check(legacyAddress)
  return hash ? toBytes20(pubkey, "utf8", toString) : pubkey
}
