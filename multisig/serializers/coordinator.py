import logging
from rest_framework import serializers
from multisig.models.coordinator import ServerIdentity

LOGGER = logging.getLogger(__name__)


class ServerIdentitySerializer(serializers.ModelSerializer):
    
    publicKey = serializers.CharField(source='public_key')

    class Meta:
        model = ServerIdentity
        fields = ['id', 'name', 'publicKey', 'message', 'signature']
