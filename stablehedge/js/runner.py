import os
import json
import logging
import requests
from subprocess import run, PIPE

# This class gets populated with functions in the javascript after loading this file
# Refer to code below

LOGGER = logging.getLogger(__name__)

class ScriptFunctionsMeta(type):
    functions_loaded = False
    functions = {}

    def __getattr__(cls, key):
        if key not in cls.functions:
            cls.functions[key] = generate_func(key)
            # raise AttributeError(key)

        return cls.functions[key]


class ScriptFunctions(metaclass=ScriptFunctionsMeta):
    pass

def generate_func(func_name):
    def func(*args):
        _input = {
            "function": func_name,
            "params": args,
        }

        try:
            response = requests.post('http://localhost:3010/', data=json.dumps(_input))
            if response.ok:
                try:
                    return response.json()
                except json.JSONDecodeError:
                    return response.content
            else:
               raise Exception(response.content.decode())
        except requests.exceptions.ConnectionError:
            pass

        process = run(['node', './stablehedge/js/src/main.js'], input=json.dumps(_input).encode(), stdout=PIPE, stderr=PIPE)
        result = None

        LOGGER.info(f"{process}")
        if process.stdout:
            try:
                result = json.loads(process.stdout)
            except json.JSONDecodeError:
                result = process.stdout
        elif process.stderr:
            raise Exception(process.stderr.decode())
        return result

    return func
