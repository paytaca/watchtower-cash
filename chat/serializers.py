from rest_framework import serializers
from chat.models import PgpInfo
from main.models import Address

class PgpInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = PgpInfo
        fields = (
            "user_id",
            "email",
            "public_key",
            "public_key_hash",
            "signature"
        )


class CreatePgpInfoSerializer(serializers.ModelSerializer):
    bch_address = serializers.CharField(max_length=70, write_only=True) 
    class Meta:
        model = PgpInfo
        fields = (
            "bch_address",
            "user_id",
            "email",
            "public_key",
            "public_key_hash",
            "signature"
        )

    def create(self, validated_data):
        address = Address.objects.get(address=validated_data['bch_address'])
        del validated_data['bch_address']
        validated_data['address'] = address
        obj = PgpInfo.objects.create(**validated_data)
        obj.save()
        return obj
