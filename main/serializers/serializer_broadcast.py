from rest_framework import serializers


class BroadcastSerializer(serializers.Serializer):
    transaction = serializers.CharField()
