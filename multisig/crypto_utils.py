from bip_utils import Bip32Secp256k1
import hashlib
from coincurve import PublicKey, PublicKeyXOnly
from hashlib import sha256

def get_address_index(path: str) -> int:
    parts = path.strip().split("/")
    last = parts[-1]
    
    if last.endswith("'"):
        # Just in case, though address index is usually not hardened
        last = last[:-1]
    
    return last

def derive_pubkey_from_xpub(xpub: str, address_index: str):
    """Derives the public key from xpub and returns its hexadecimal representation."""
    key = Bip32Secp256k1.FromExtendedKey(xpub)
    public_key = key.DerivePath(address_index or '0').PublicKey()
    # Return the hexadecimal representation of the public key
    return public_key.RawCompressed()

def verify_signature(message: str, signature_hex: str, xpub: str, address_index: str, algo: str = "ecdsa") -> bool:
    """Verifies the signature using the given xpub, address index, and algorithm."""
    try:
        public_key = derive_pubkey_from_xpub(xpub, address_index)
        signature = bytes.fromhex(signature_hex)
        message_bytes = message.encode('utf-8')        
        # message_hash = hashlib.sha256()
        # message_hash.update(message_bytes)
        # message_hash = message_hash.digest()
        
        if not algo or algo == 'ecdsa':
            pubkey = PublicKey(public_key.ToBytes())
            return pubkey.verify(signature, message_bytes)
        elif algo == "schnorr":
            # Pass for now, always sig verification failure using coincurve
            # pubkey = PublicKeyXOnly(public_key.ToBytes()[1:])
            # return pubkey.verify(signature, message_hash)
            raise Exception('Unsupported algorith "schnorr"!')
        else:
            return False
    except Exception as e:
        print(f"Error during verification: {e}")
        return False
