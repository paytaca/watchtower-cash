# multisig/crypto_utils.py
import bip32utils
from coincurve import PublicKey
from hashlib import sha256

def get_address_index(path: str) -> int:
    parts = path.strip().split("/")
    last = parts[-1]
    
    if last.endswith("'"):
        # Just in case, though address index is usually not hardened
        last = last[:-1]
    
    return int(last)


def derive_pubkey_from_xpub(xpub: str, derivation_path: int):
    """Derives the public key from xpub."""
    key = bip32utils.BIP32Key.fromExtendedKey(xpub, public=True)
    address_index = 0
    if derivation_path:
      address_index = get_address_index(derivation_path)
    return key.ChildKey(0).ChildKey(address_index).PublicKey()

def verify_signature(message: str, signature_hex: str, xpub: str, derivation_path: str, algo: str = "ecdsa") -> bool:
    """Verifies the signature using the given xpub, derivation path, and algorithm."""
    try:
        pubkey_bytes = derive_pubkey_from_xpub(xpub, derivation_path)
        
        pubkey = PublicKey(pubkey_bytes)
        
        signature = bytes.fromhex(signature_hex)
        message_bytes = message.encode('utf-8')

        if not algo or algo == 'ecdsa':
            return pubkey.verify(signature, message_hash)
        elif algo == "schnorr":
            return pubkey.schnorr_verify(message_hash, signature)
        else:
            return False
    except Exception as e:
        print(f"Error during verification: {e}")
        return False
