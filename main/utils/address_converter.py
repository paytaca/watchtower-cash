from subprocess import Popen, PIPE

from django.conf import settings


def bch_address_converter(bch_addr, to_token_addr=True):
    cmd = f'node main/js/bch-addr-converter.js {bch_addr} {settings.BCH_NETWORK} {to_token_addr}'
    p = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE)
    stdout, stderr = p.communicate()

    if stderr:
        return ''
    else:
        return stdout.decode('utf8').split('\n')[0]
