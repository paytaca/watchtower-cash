import re
from cashaddress.convert import Address, InvalidAddress
from rest_framework import serializers

def valid_hex(value):
    regx = re.compile("^[0-9a-fA-F]*$")
    return bool(regx.search(value))


class ValidTxHash:
    def __call__(self, value):
        if not valid_hex(value) or len(value) != 64:
            raise serializers.ValidationError("Invalid transaction hash")


class ValidAddress:
    TYPE_LEGACY = "legacy"
    TYPE_CASHADDR = "cash_address"

    def __init__(self, addr_type=None):
        self.addr_type = addr_type

    def __call__(self, value):
        result = False
        if self.addr_type == self.TYPE_LEGACY and not self.valid_legacy_address(value):
            raise serializers.ValidationError("Invalid legacy address")
        
        if self.addr_type == self.TYPE_CASHADDR and not self.valid_cashaddress(value):
            raise serializers.ValidationError("Invalid cash address")

        if not self.valid_legacy_address(value) and not self.valid_cashaddress(value):
            raise serializers.ValidationError("Invalid address")

        return True
        
    def valid_legacy_address(self, value):
        try:
            Address._legacy_string(value)
            return True
        except InvalidAddress:
            return False

    def valid_cashaddress(self, value):
        try:
            Address._cash_string(value)
            return True
        except InvalidAddress:
            return False