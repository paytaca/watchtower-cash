from main.models import Token
from rest_framework import serializers, exceptions

class TokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Token
        fields = [
            'name',
            'tokenid',
            'confirmation_limit'
        ]