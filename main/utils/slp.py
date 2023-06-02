from subprocess import Popen, PIPE
import json


def get_slp_token_details(token_id):
    cmd = f'node main/js/get-slp-token-details.js {token_id}'
    p = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE)
    stdout, stderr = p.communicate()

    if stderr:
        return {}
    return json.loads(stdout.decode('utf8'))
