from hashlib import sha256

def get_tx_hash(tx_hex):
    tx_hex_bytes = bytes.fromhex(tx_hex)
    hash1 = sha256(tx_hex_bytes).digest()
    hash2 = sha256(hash1).digest()
    d = bytearray(hash2)
    d.reverse()
    return d.hex()
