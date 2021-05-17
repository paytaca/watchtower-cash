import cashaddress
from cashaddress import convert
from cashaddress.crypto import convertbits, calculate_checksum, b32encode

def get_address_info(any_address):
    legacy = convert.to_legacy_address(any_address)
    bch_address = convert.to_cash_address(legacy)
    address = cashaddress.convert.Address.from_string(bch_address)
    version_int = address._address_type('cash', address.version)[1]
    payload = [version_int] + address.payload
    payload = convertbits(payload, 8, 5)
    prefix = 'simpleledger'
    checksum = calculate_checksum(prefix, payload)
    simple_ledger_address = prefix + ':' + b32encode(payload + checksum)
    return {
        'bitcoincash_address': bch_address,
        'legacy_address': legacy,
        'simple_ledger_address': simple_ledger_address
    }
