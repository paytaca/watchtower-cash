import re

def is_hex_string(value):
    return re.match("0x[0-9a-f]*", value)


def int_to_hex(value):
    return "0x{:02x}".format(value)

def hex_to_int(hex_string):
    return int(hex_string, 16)

def pad_hex_string(value, target_length=0):
    if not is_hex_string(value):
        return value
    value = value.replace("0x", "")
    value = "0" * (target_length - len(value)) + value
    value = "0x" + value
    return value

def format_block_number(value, exclude_names=False):
    block_names = ["latest", "pending", "earliest"]
    if value in block_names and not exclude_names:
        return value

    if isinstance(value, int):
        return int_to_hex(value)

    if is_hex_string(str(value)):
        return str(value)
