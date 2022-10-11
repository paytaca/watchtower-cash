import hashlib
import base58
from cashaddress import convert

def hash160(hex_str):
    sha = hashlib.sha256()
    rip = hashlib.new('ripemd160')
    sha.update(hex_str)
    rip.update( sha.digest() )
    return rip.hexdigest()  # .hexdigest() is hex ASCII


def match_pubkey_to_cash_address(pubkey, cash_addr):
    return pubkey_to_cashaddr(pubkey) == cash_addr

def pubkey_to_cashaddr(pubkey):
    # src: https://gist.github.com/circulosmeos/ef6497fd3344c2c2508b92bb9831173f
    hex_str = bytearray.fromhex(pubkey)

    key_hash = '00' + hash160(hex_str)

    sha = hashlib.sha256()

    sha.update( bytearray.fromhex(key_hash) )

    checksum = sha.digest()
    sha = hashlib.sha256()
    sha.update(checksum)
    checksum = sha.hexdigest()[0:8]

    legacy_addr = (base58.b58encode( bytes(bytearray.fromhex(key_hash + checksum)) )).decode('utf-8')
    return convert.to_cash_address(legacy_addr)
