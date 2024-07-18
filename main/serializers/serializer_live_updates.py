from rest_framework import serializers

from main.models import Address, Subscription


LIVE_UPDATES_PAYMENT_TYPES = [
    'qr_scanned',
    'cancel_payment',
    'selecting_vouchers',
    'sending_vouchers',
]

vouchers_structure = '''
total_count: 0,
total_amount: 0, // BCH
selected: [ { amount: 0 } ] // BCH
'''


class LiveUpdatesPaymentSerializer(serializers.Serializer):
    address = serializers.CharField()
    update_type = serializers.ChoiceField(choices=LIVE_UPDATES_PAYMENT_TYPES)
    vouchers = serializers.JSONField(required=False, help_text=vouchers_structure)

    def validate_address(self, value):
        address = Address.objects.filter(address=value)
        if address.exists():
            subscription = Subscription.objects.filter(address=address.first())
            if subscription.exists():
                return value
        raise serializers.ValidationError('Address is not subscribed to watchtower!')