import os
import json
import logging
from subprocess import run, PIPE

# This class gets populated with functions in the javascript after loading this file
# Refer to code below

LOGGER = logging.getLogger(__name__)

class AnyhedgeFunctionsMeta(type):
    functions_loaded = False
    functions = {}

    def load_anyhedge_functions(cls):
        print("loading anyhedge functions")
        process = run(['node', '/code/anyhedge/js/src/load.js'], stdout=PIPE)
        functions = []
        if process.stdout:
            functions = json.loads(process.stdout)

        for function in functions:
            cls.functions[function] = generate_func(function)

        cls.functions_loaded = True

    def __getattr__(cls, key):
        if key == "__load_functions__":
            return cls.load_anyhedge_functions

        if key not in cls.functions:
            cls.functions[key] = generate_func(key)
            # raise AttributeError(key)

        return cls.functions[key]


class AnyhedgeFunctions(metaclass=AnyhedgeFunctionsMeta):
    pass

def generate_func(func_name):
    def func(*args):
        _input = {
            "function": func_name,
            "params": args,
        }
        process = run(['node', './anyhedge/js/src/main.js'], input=json.dumps(_input).encode(), stdout=PIPE, stderr=PIPE)
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
