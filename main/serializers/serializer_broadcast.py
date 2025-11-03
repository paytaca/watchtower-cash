from rest_framework import serializers


class BroadcastSerializer(serializers.Serializer):
    transaction = serializers.CharField()
    price_id = serializers.IntegerField(required=False, allow_null=True)
    output_fiat_amounts = serializers.JSONField(
        required=False, 
        allow_null=True,
        help_text='Map of output index to fiat amount details. Format: {"0": {"fiat_amount": "100.50", "fiat_currency": "PHP", "recipient": "bitcoincash:qr..."}}'
    )


class TransactionOutputFiatAmountsSerializer(serializers.Serializer):
    """Serializer for saving fiat amounts to an existing transaction broadcast"""
    txid = serializers.CharField(max_length=70, help_text='Transaction ID')
    output_fiat_amounts = serializers.JSONField(
        help_text='Map of output index to fiat amount details. Format: {"0": {"fiat_amount": "100.50", "fiat_currency": "PHP", "recipient": "bitcoincash:qr..."}}'
    )
