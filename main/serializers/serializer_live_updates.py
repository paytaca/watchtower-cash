from rest_framework import serializers

LIVE_UPDATES_PAYMENT_TYPES = [
    'qr_scanned',
    'claiming_voucher',
    'voucher_received'
]


class LiveUpdatesPaymentSerializer(serializers.Serializer):
    address = serializers.CharField()


class LiveUpdatesPaymentResponseSerializer(serializers.Serializer):
    address = serializers.CharField()
    update_type = serializers.ChoiceField(choices=LIVE_UPDATES_PAYMENT_TYPES)