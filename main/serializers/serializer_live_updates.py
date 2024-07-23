from rest_framework import serializers

from main.models import Address, Subscription


LIVE_UPDATES_PAYMENT_TYPES = [
    'qr_scanned',
    'cancel_payment',
    'sending_payment',
] 


class LiveUpdatesPaymentSerializer(serializers.Serializer):
    address = serializers.CharField()
    update_type = serializers.ChoiceField(choices=LIVE_UPDATES_PAYMENT_TYPES)

    def validate_address(self, value):
        address = Address.objects.filter(address=value)
        if address.exists():
            subscription = Subscription.objects.filter(address=address.first())
            if subscription.exists():
                return value
        raise serializers.ValidationError('Address is not subscribed to watchtower!')