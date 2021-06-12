from cashaddress.crypto import convertbits, calculate_checksum, b32encode
import cashaddress


def convert_bch_to_slp_address(bch_address):
    address = cashaddress.convert.Address.from_string(bch_address)
    version_int = address._address_type('cash', address.version)[1]
    payload = [version_int] + address.payload
    payload = convertbits(payload, 8, 5)
    prefix = 'simpleledger'
    checksum = calculate_checksum(prefix, payload)
    return prefix + ':' + b32encode(payload + checksum)
