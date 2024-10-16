import re
import json
import decimal

def parse_bigint_string(value):
    if not isinstance(value, str):
        return value

    match_result = re.match("<bigint\:\s*(\d+)n>", value)

    if not match_result:
        return value

    number = match_result.group(1)
    return decimal.Decimal(number)

# https://blag.nullteilerfrei.de/2020/07/11/custom-jsonencoder-and-jsondecoder-to-handle-datetime-in-pythons-json-library/
class CustomAnyhedgeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, decimal.Decimal) and obj % 1 == 0:
            return f"<bigint: {obj}n>"

class CustomAnyhedgeDecoder(json.JSONDecoder):
    def __init__(self, *args, **kwargs):
        super().__init__(object_hook=self.try_bigint, *args, **kwargs)

    @staticmethod
    def try_bigint(d):
        ret = {}
        for key, value in d.items():
            ret[key] = parse_bigint_string(value)
        return ret

class AnyhedgeJSONParser:
    @staticmethod
    def loads(*args, **kwargs):
        result = json.loads(*args, cls=CustomAnyhedgeDecoder, **kwargs)
        return parse_bigint_string(result)

    @staticmethod
    def dumps(*args, **kwargs):
        return json.dumps(*args, cls=CustomAnyhedgeEncoder, **kwargs)

    @classmethod
    def parse(cls, data):
        if not isinstance(data, (str, bytes)):
            data = json.dumps(data)

        data = parse_bigint_string(data)
        return cls.loads(data)
