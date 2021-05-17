from main.models import SLPToken
from rest_framework import serializers, exceptions

class SLPTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = SLPToken
        fields = [
            'name',
            'tokenid',
            'confirmation_limit'
        ]