from subprocess import Popen, PIPE

from django.conf import settings


def token_addr_converter(bch_addr, to_token_addr=True):
    cmd = f'node main/js/token-addr-converter.js {bch_addr} {settings.BCH_NETWORK} {to_token_addr}'
    p = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE)
    stdout, stderr = p.communicate()

    if stderr:
        return ''
    return stdout.decode('utf8').split('\n')[0]


def bch_to_slp_addr(bch_addr):
    cmd = f'node main/js/bch-to-slp-addr.js {bch_addr}'
    p = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE)
    stdout, stderr = p.communicate()

    if stderr:
        return ''
    return stdout.decode('utf8').split('\n')[0]
