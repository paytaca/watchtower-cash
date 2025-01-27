from rest_framework import serializers
from rampp2p.serializers import FiatCurrencySerializer
import rampp2p.models as models

class ArbiterSerializer(serializers.ModelSerializer):
    id = serializers.CharField(read_only=True)
    wallet_hash = serializers.CharField(required=False, write_only=True)
    name = serializers.CharField(required=False)
    chat_identity_id = serializers.CharField(required=False)
    public_key = serializers.CharField(required=False)
    address = serializers.CharField(required=False)
    address_path = serializers.CharField(required=False)
    inactive_until = serializers.DateTimeField(required=False)
    is_disabled = serializers.BooleanField(read_only=True)
    fiat_currencies = FiatCurrencySerializer(many=True, read_only=True)
    rating = serializers.SerializerMethodField()

    class Meta:
        model = models.Arbiter
        fields = [
            'id',
            'wallet_hash',
            'name',
            'chat_identity_id',
            'public_key',
            'address',
            'address_path',
            'inactive_until',
            'is_disabled',
            'fiat_currencies',
            'rating',
            'is_online',
            'last_online_at'
        ]

    def get_rating(self, obj):
        return obj.average_rating()