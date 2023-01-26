from rest_framework import serializers
from chat.models import ChatIdentity
from main.models import Address

class ChatIdentitySerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatIdentity
        fields = (
            "user_id",
            "email",
            "public_key",
            "public_key_hash",
            "signature"
        )


class CreateChatIdentitySerializer(serializers.ModelSerializer):
    bch_address = serializers.CharField(max_length=70, write_only=True) 
    class Meta:
        model = ChatIdentity
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
        obj = ChatIdentity.objects.create(**validated_data)
        obj.save()
        return obj
