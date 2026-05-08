from rest_framework import serializers
from main.serializers.serializer_address_scan import WalletAddressSetSerializer


class AdvanceSubscriptionSerializer(serializers.Serializer):
    wallet_hash = serializers.CharField(max_length=200)
    project_id = serializers.CharField(max_length=200, required=False, allow_blank=True)
    address_sets = WalletAddressSetSerializer(many=True)
    
    def validate_address_sets(self, value):
        """Validate max 50 pairs and sequential indices"""
        if len(value) > 50:
            raise serializers.ValidationError("Maximum 50 address pairs allowed")
        
        if len(value) == 0:
            raise serializers.ValidationError("At least one address pair is required")
        
        # Validate sequential indices
        indices = sorted([item['address_index'] for item in value])
        expected_indices = list(range(indices[0], indices[0] + len(indices)))
        
        if indices != expected_indices:
            raise serializers.ValidationError(
                "Address indices must be sequential. "
                f"Expected indices from {indices[0]} to {indices[0] + len(indices) - 1}, "
                f"but got: {indices}"
            )
        
        return value


class AdvanceSubscriptionResponseSerializer(serializers.Serializer):
    address_set = WalletAddressSetSerializer()
    success = serializers.BooleanField()
    skipped = serializers.BooleanField()
    error = serializers.CharField(required=False, allow_blank=True)
