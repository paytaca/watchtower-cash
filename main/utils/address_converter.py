# from subprocess import Popen, PIPE
import requests
import bitcoin
from django.conf import settings

from cashaddress import convert


def bch_address_converter(bch_addr, to_token_addr=True):
    # cmd = f'node main/js/bch-addr-converter.js {bch_addr} {to_token_addr}'
    #p = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE)
    #stdout, stderr = p.communicate()

    converted_address = ''
    url = f'http://localhost:3000/convert-address/{bch_addr}?to_token={to_token_addr}'
    resp = requests.get(url)
    if resp.status_code == 200:
        converted_address = resp.text
    return converted_address

def pubkey_to_bch_address(pubkey, to_token_addr=False):
    legacy_address = bitcoin.pubkey_to_address(pubkey)
    cash_address = convert.to_cash_address(legacy_address)
    if not to_token_addr:
        return cash_address
    return bch_address_converter(cash_address, to_token_addr=to_token_addr)

def address_to_locking_bytecode(address):
    cash_address = convert.to_cash_address(address)
    url = f'http://localhost:3000/to-locking-bytecode/{cash_address}'
    resp = requests.get(url)
    result = resp.json()
    if not result["success"]: raise Exception(result["error"])
    return result["bytecode"]
