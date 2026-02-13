import logging
from multisig.auth.auth import parse_signatures
from multisig.js_client import verify_signature
from django.utils import timezone
from rest_framework import serializers
from multisig.models.coordinator import KeyRecord, ServerIdentity

LOGGER = logging.getLogger(__name__)


class ServerIdentitySerializer(serializers.ModelSerializer):
    
    publicKey = serializers.CharField(source='public_key')
    
    def validate(self, attrs):
        public_key = attrs.get('public_key')
        signature = attrs.get('signature')
        message = attrs.get('message')
        if signature:
            response = verify_signature(
                message,
                public_key,
                parse_signatures(signature)
            )
            result = response.json()
            if result['success']:
                return attrs
            raise serializers.ValidationError(f"Error in verifying signature: {public_key}")
        return attrs

    def create(self, validated_data):
        return super().create(validated_data)

    class Meta:
        model = ServerIdentity
        fields = ['id', 'name', 'publicKey', 'message', 'signature']

class KeyRecordSerializer(serializers.Serializer):
    publisher = serializers.PrimaryKeyRelatedField(queryset=ServerIdentity.objects.all(), required=False)
    recipient = serializers.PrimaryKeyRelatedField(queryset=ServerIdentity.objects.all(), required=False)
    key_record = serializers.CharField()

    class Meta:
        model = KeyRecord
        fields = ['id', 'publisher', 'recipient', 'key_record']