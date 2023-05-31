from subprocess import Popen, PIPE
import json


def parse_slp_op(op_ret_hash):
    cmd = f'node main/js/parse-slp-op.js {op_ret_hash}'
    p = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE)
    stdout, stderr = p.communicate()

    if stderr:
        return {}
    return json.loads(stdout.decode('utf8'))
