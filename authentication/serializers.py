from rest_framework import serializers

class UserSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    chat_identity_id = serializers.IntegerField()
    public_key = serializers.CharField()
    name = serializers.CharField()
    address = serializers.CharField()
    address_path = serializers.CharField()
    is_arbiter = serializers.BooleanField(required=False)
    is_authenticated = serializers.BooleanField(required=False)