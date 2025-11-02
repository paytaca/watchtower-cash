from rest_framework import serializers


class BroadcastSerializer(serializers.Serializer):
    transaction = serializers.CharField()
    price_id = serializers.IntegerField(required=False, allow_null=True)
