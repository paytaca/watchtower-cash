"""Run only the bundled escrow generator with validated constructor arguments."""
import json
from decimal import Decimal
from pathlib import Path
import re
import subprocess

from ecdsa import SECP256k1, VerifyingKey
from ecdsa.errors import MalformedPointError


def generate_contract_address(arbiter_pubkey, buyer_pubkey, seller_pubkey,
                              timestamp, service_fee, arbitration_fee):
    keys = (arbiter_pubkey, buyer_pubkey, seller_pubkey)
    for key in keys:
        if not isinstance(key, str) or not re.fullmatch(r'(02|03)[0-9a-fA-F]{64}', key):
            raise ValueError('A compressed secp256k1 public key is required.')
        try:
            VerifyingKey.from_string(bytes.fromhex(key), curve=SECP256k1)
        except (ValueError, MalformedPointError) as err:
            raise ValueError('Invalid contract public key.') from err

    if type(timestamp) not in (str, int, float):
        raise ValueError('Invalid contract timestamp.')
    timestamp_text = str(timestamp)
    if (not re.fullmatch(r'[0-9]{1,12}(\.[0-9]{1,6})?', timestamp_text)
            or not 0 <= Decimal(timestamp_text) <= 253402300799):
        raise ValueError('Invalid contract timestamp.')

    for fee in (service_fee, arbitration_fee):
        if type(fee) is not int or not 0 <= fee <= 2100000000000000:
            raise ValueError('Contract fees must be nonnegative integer satoshis.')

    script = Path(__file__).resolve().parent / 'js' / 'src' / 'escrow.js'
    result = subprocess.run(
        ['node', str(script), *keys, timestamp_text, str(service_fee), str(arbitration_fee)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        shell=False, check=True, timeout=30,
    )
    output = json.loads(result.stdout.decode('utf-8'))
    if not isinstance(output, dict):
        raise ValueError('Invalid escrow generator response.')
    return {'result': output, 'error': result.stderr.decode('utf-8')}
