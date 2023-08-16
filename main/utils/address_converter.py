# from subprocess import Popen, PIPE
import requests
from django.conf import settings


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
