import json
import requests
from internal_services.client import post_script_request

# This class gets populated lazily with function proxies. The JS server resolves
# the function name and returns an error for unknown functions.

class AnyhedgeFunctionsMeta(type):
    functions = {}

    def __getattr__(cls, key):
        if key.startswith("_"):
            raise AttributeError(key)

        if key not in cls.functions:
            cls.functions[key] = generate_func(key)

        return cls.functions[key]


class AnyhedgeFunctions(metaclass=AnyhedgeFunctionsMeta):
    pass

def generate_func(func_name):
    def func(*args):
        _input = {
            "function": func_name,
            "params": args,
        }

        try:
            response = post_script_request('anyhedge', _input)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as err:
            raise RuntimeError(
                "Anyhedge JS server is unavailable at http://localhost:3020/"
            ) from err

        if not response.ok:
            raise Exception(response.content.decode())

        try:
            return response.json()
        except json.JSONDecodeError:
            return response.content

    return func
