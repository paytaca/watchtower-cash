import binascii
import hashlib
import base58

from cashaddress import convert

def hash160(data):
    """Performs a RIPEMD-160 hash after a SHA-256 hash (i.e., Bitcoin's HASH160)."""
    sha256_hash = hashlib.sha256(data).digest()
    ripemd160_hash = hashlib.new('ripemd160', sha256_hash).digest()
    return ripemd160_hash

def base58check_encode(data):
    """Encodes data in Base58Check format, adding a 4-byte checksum."""
    checksum = hashlib.sha256(hashlib.sha256(data).digest()).digest()[:4]
    return base58.b58encode(data + checksum)

def locking_bytecode_to_address(script_pubkey_hex):
    script_pubkey = binascii.unhexlify(script_pubkey_hex)
    # P2PKH format: OP_DUP OP_HASH160 <PublicKeyHash> OP_EQUALVERIFY OP_CHECKSIG
    if script_pubkey[:3] == b'\x76\xa9\x14' and script_pubkey[-2:] == b'\x88\xac':
        public_key_hash = script_pubkey[3:-2]  # Extract the public key hash (20 bytes)
        prefix = b'\x00'  # Mainnet P2PKH address prefix (0x00)
        return base58check_encode(prefix + public_key_hash).decode('utf-8')

    # P2SH format: OP_HASH160 <ScriptHash> OP_EQUAL
    elif script_pubkey[:2] == b'\xa9\x14' and script_pubkey[-1:] == b'\x87':
        script_hash = script_pubkey[2:-1]  # Extract the script hash (20 bytes)
        prefix = b'\x05'  # Mainnet P2SH address prefix (0x05)
        return base58check_encode(prefix + script_hash).decode('utf-8')

    else:
        raise ValueError("Unknown or unsupported scriptPubKey format")


def to_cash_address(address, testnet=None):
    if testnet is None:
        return convert.to_cash_address(address)

    address_obj = convert.Address.from_string(address)
    TESTNET_POSTFIX = "-TESTNET"
    if testnet:
        address_obj.prefix = convert.Address.TESTNET_PREFIX
        if not address_obj.version.endswith(TESTNET_POSTFIX):
            address_obj.version += TESTNET_POSTFIX
    else:
        address_obj.prefix = convert.Address.MAINNET_PREFIX
        if address_obj.version.endswith(TESTNET_POSTFIX):
            address_obj.version = address_obj.version.replace(TESTNET_POSTFIX, "")

    return address_obj.cash_address()
