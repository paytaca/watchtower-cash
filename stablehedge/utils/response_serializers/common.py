from rest_framework import serializers

class CommonResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(read_only=True)
    error = serializers.CharField(read_only=True)
