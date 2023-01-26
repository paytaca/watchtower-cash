from rest_framework import serializers

from main.models import TransactionMetaAttribute


class TransactionMetaAttributeSerializer(serializers.ModelSerializer):
    remove = serializers.BooleanField(default=False)
    
    class Meta:
        model = TransactionMetaAttribute
        fields = [
            "txid",
            "wallet_hash",
            "key",
            "value",
            "remove",
            "system_generated",
        ]
        extra_kwargs = {
            "system_generated": {
                "read_only": True,
            },
            "value": {
                "required": False,
            }
        }

    def get_unique_together_validators(self):
        """Overriding method to disable unique together checks"""
        return []

    def validate(self, data):
        remove = data["remove"]
        if not remove and not data.get("value", None):
            raise serializers.ValidationError("'value' or 'remove' required")
        return data

    def save(self):
        validated_data = self.validated_data
        remove = validated_data["remove"]
        if remove:
            TransactionMetaAttribute.objects.filter(
                txid=validated_data["txid"],
                wallet_hash=validated_data["wallet_hash"],
                key=validated_data["key"],
                system_generated=False,
            ).delete()
            return

        instance, _ = TransactionMetaAttribute.objects.update_or_create(
            txid=validated_data["txid"],
            wallet_hash=validated_data["wallet_hash"],
            key=validated_data["key"],
            system_generated=False,
            defaults=dict(
                value=validated_data["value"],
            )
        )
        self.instance = instance

        return instance
