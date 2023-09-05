import os
import json
import logging
from subprocess import run, PIPE

# This class gets populated with functions in the javascript after loading this file
# Refer to code below

LOGGER = logging.getLogger(__name__)


class ScriptFunctionsMeta(type):
    functions = {}

    def __getattr__(cls, key):
        if key not in cls.functions:
            cls.functions[key] = generate_func(key)

        return cls.functions[key]


class ScriptFunctions(metaclass=ScriptFunctionsMeta):
    pass


def generate_func(func_name):
    def func(*args):
        _input = {
            "function": func_name,
            "params": args,
        }
        process = run(
            [
                'node',
                './vouchers/js/src/main.js'
            ],
            input=json.dumps(_input).encode(),
            stdout=PIPE,
            stderr=PIPE
        )
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
