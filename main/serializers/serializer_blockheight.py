
from rest_framework import serializers, exceptions

class BlockHeightSerializer(serializers.Serializer):
    number = serializers.IntegerField(default=0)
    