import os
import json
import functools

@functools.lru_cache(maxsize=None)
def get_token_abi(erc_number):
    dir_path = os.path.dirname(os.path.realpath(__file__))

    filename = f"{dir_path}/erc{erc_number}.json"
    if not os.path.exists(filename):
        return

    with open(filename, "r") as f:
        try:
            return json.load(f)
        except json.decoder.JSONDecodeError:
            return
