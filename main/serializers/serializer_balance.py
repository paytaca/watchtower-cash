from rest_framework import serializers, exceptions


class MultisigInputInfoSerializer(serializers.Serializer):
    size =serializers.IntegerField(required=False, default=0)
    signers = serializers.IntegerField(required=False, default=0)
    count = serializers.IntegerField(required=False, default=0)


class TxFeeCalculatorSerializer(serializers.Serializer):
    # p2pkh_input_count = serializers.IntegerField(required=False, default=0)
    # multisig_inputs = MultisigInputInfoSerializer(required=False, many=True)

    p2pkh_output_count = serializers.IntegerField(required=False, default=2)
    p2sh_output_count = serializers.IntegerField(required=False, default=0)
    push_data = serializers.ListField(
        child=serializers.CharField(
            help_text="List of outputs containing push data. Input can be in hex or utf8",
        ),
        required=False,
    )


class BalanceResponseSerializer(serializers.Serializer):
    valid = serializers.BooleanField(read_only=True)
    balance = serializers.FloatField(read_only=True)
    spendable = serializers.FloatField(read_only=True)
    token_id = serializers.CharField(read_only=True)
    wallet = serializers.CharField(read_only=True)
    address = serializers.CharField(read_only=True)
