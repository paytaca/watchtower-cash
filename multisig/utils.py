import logging
import hashlib
from bip_utils import Bip32Secp256k1
from coincurve import PublicKey
from bip_utils import Bip32Secp256k1, Hash160
from collections import defaultdict

LOGGER = logging.getLogger(__name__)
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
    return public_key.RawCompressed().ToHex()

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

def create_redeem_script(pubkeys, m: int):
    m = format(80 + m, 'x')
    n = format(80 + len(pubkeys), 'x')
    print('m', m)
    print('n', n)
    script = m
    for pubkey in pubkeys:
        print(pubkey)
        script += '21' + pubkey
    script += n + 'ae'
    return script
    
def get_locking_bytecode(redeem_script) -> str:
    '''
    Returns the locking bytecode as hex string
    '''
    return Hash160().QuickDigest(bytes.fromhex(redeem_script)).hex()

def get_locking_script(locking_bytecode: str):
    return 'a9' + format(len(bytes.fromhex(locking_bytecode)), 'x') + locking_bytecode + '87'


def get_multisig_wallet_locking_script(template: dict, locking_data: dict):
    m = int(template['scripts']['lock']['script'].split('\n')[0].split('_')[1])
    address_index = locking_data['hdKeys']['addressIndex'] or '0'
    xpubs = locking_data['hdKeys']['hdPublicKeys']
    sorted_xpubs = [v for k, v in sorted(xpubs.items(), key=lambda item: int(item[0].split('_')[1]))]
    
    pubkeys = [derive_pubkey_from_xpub(xpub, str(address_index)) for xpub in sorted_xpubs]
    LOGGER.info(pubkeys)

    redeem_script = create_redeem_script(pubkeys, m)
    locking_bytecode = get_locking_bytecode(redeem_script)
    locking_script = get_locking_script(locking_bytecode)

    return locking_script

# Signatures check utils

def group_signatures_by_input(signatures):
    """
    Organize signatures by input index.
    Returns: {input_index: set of signer IDs}
    """
    grouped = defaultdict(set)
    for sig in signatures:
        input_index = sig["inputIndex"]
        signer = sig["signer"]
        grouped[input_index].add(signer)
    return grouped

def is_input_fully_signed(input_index, grouped_signatures, required_m):
    """
    Check if a specific input has enough unique signatures.
    """
    signers = grouped_signatures.get(input_index, set())
    return len(signers) >= required_m

def is_transaction_fully_signed(signatures, required_signatures):
    """
    Check if all inputs in the transaction are fully signed.
    """
    grouped_signatures = group_signatures_by_input(signatures)
    for input_index, required_m in required_signatures.items():
        if not is_input_fully_signed(input_index, grouped_signatures, required_m):
            return False
    return True


def generate_transaction_hash(transaction_hex):
    """
    Generates the transaction hash (txid) for a bitcoin-style transaction.

    This function double-SHA256 hashes the transaction_hex, then reverses
    the resulting bytes, following the convention used in Bitcoin and 
    similar to the implementation in @bitauth/libauth's hashTransaction.

    Args:
        transaction_hex (str): The encoded transaction in hex string format.

    Returns:
        str: The hex-encoded txid (transaction hash).
    """
    return hashlib.sha256(
        hashlib.sha256(
            bytes.fromhex(transaction_hex)
        ).digest()
    ).digest()[::-1].hex()


