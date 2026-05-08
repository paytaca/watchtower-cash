from rest_framework import serializers


class AddressPairSerializer(serializers.Serializer):
    """Single address pair (receiving + change)"""
    receiving = serializers.CharField(max_length=200)
    change = serializers.CharField(max_length=200)


class AdvanceSubscriptionSerializer(serializers.Serializer):
    """
    Subscribe multiple address pairs in advance.
    Format matches the standard subscription API but accepts arrays.
    """
    wallet_hash = serializers.CharField(max_length=200)
    project_id = serializers.CharField(max_length=200, required=False, allow_blank=True)
    start_index = serializers.IntegerField(min_value=0)
    address_pairs = serializers.ListField(
        child=AddressPairSerializer(),
        min_length=1,
        max_length=50
    )
    
    def validate(self, data):
        """Validate that we have the right number of pairs"""
        if len(data['address_pairs']) > 50:
            raise serializers.ValidationError("Maximum 50 address pairs allowed")
        return data


class AdvanceSubscriptionResponseSerializer(serializers.Serializer):
    """Response for advance subscription request"""
    subscribed = serializers.IntegerField()
    skipped = serializers.IntegerField()
    start_index = serializers.IntegerField()
    end_index = serializers.IntegerField()
