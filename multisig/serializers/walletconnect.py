from rest_framework import serializers
from multisig.models.walletconnect import WalletConnectSession

class WalletConnectSessionSerializer(serializers.ModelSerializer):
    walletName = serializers.CharField(source='wallet.name', read_only=True)
    peerName = serializers.CharField(source='peer_name')
    peerUrl = serializers.CharField(source='peer_url')
    originName = serializers.CharField(source='origin_name')
    originUrl = serializers.CharField(source='origin_url')
    isActive = serializers.BooleanField(source='is_active', required=False)
    createdAt = serializers.DateTimeField(source='created_at', required=False)
    updatedAt = serializers.DateTimeField(source='updated_at', required=False)

    class Meta:
        model = WalletConnectSession
        fields = [
            'id',
            'topic',
            'wallet',           
            'walletName',       
            'accounts',
            'peerName',
            'peerUrl',
            'originName',
            'originUrl',
            'expiry',
            'isActive',
            'createdAt',
            'updatedAt',
        ]
        read_only_fields = ['id', 'createdAt', 'updatedAt', 'isActive', 'walletName']