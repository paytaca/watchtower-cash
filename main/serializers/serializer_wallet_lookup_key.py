from rest_framework import serializers

from main.models import WalletLookupKey


class WalletLookupKeyCreateSerializer(serializers.ModelSerializer):
    """
    Mint a lookup key for the authenticated wallet.

    `wallet` is never read from the request body -- the view injects it from
    request.user so a caller cannot bind a key to somebody else's wallet.
    """

    class Meta:
        model = WalletLookupKey
        fields = ['label', 'wallet']
        extra_kwargs = {
            'wallet': {'required': False},
        }


class WalletLookupKeyCreatedSerializer(serializers.ModelSerializer):
    """
    The create response. This is the ONLY place the raw key appears -- it is
    never stored, so it cannot be retrieved again.
    """
    lookup_key = serializers.CharField(read_only=True)

    class Meta:
        model = WalletLookupKey
        fields = ['id', 'lookup_key', 'label', 'date_created']


class WalletLookupKeySerializer(serializers.ModelSerializer):
    """Read-only representation. The digest is truncated for display."""

    key_hash = serializers.SerializerMethodField()

    class Meta:
        model = WalletLookupKey
        fields = ['id', 'label', 'key_hash', 'date_created', 'last_used_at']

    def get_key_hash(self, obj):
        return f'{obj.key_hash[:8]}...'


class WalletLookupKeyAssetBalanceSerializer(serializers.Serializer):
    asset_id = serializers.CharField(read_only=True)
    balance = serializers.FloatField(read_only=True)
    decimals = serializers.IntegerField(read_only=True, required=False)
    found = serializers.BooleanField(read_only=True, required=False)
    name = serializers.CharField(read_only=True, required=False)
    symbol = serializers.CharField(read_only=True, required=False)


class WalletLookupKeyBalanceSerializer(serializers.Serializer):
    wallet_hash = serializers.CharField(read_only=True)
    bch = serializers.DictField(read_only=True)
    assets = WalletLookupKeyAssetBalanceSerializer(many=True, read_only=True)
