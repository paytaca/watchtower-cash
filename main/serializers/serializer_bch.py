from main.models import BchAddress
from rest_framework import serializers, exceptions

class BchAddress(serializers.ModelSerializer):
    model = BchAddress
    fields = ['address',]