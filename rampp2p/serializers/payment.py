from rest_framework import serializers
from ..models.payment import PaymentMethod, PaymentType
from ..models.peer import Peer

class RelatedPaymentMethodSerializer(serializers.ModelSerializer):
    payment_type = serializers.SlugRelatedField(slug_field="name", queryset=PaymentType.objects.all())
    class Meta:
        model = PaymentMethod
        fields = ['id', 'payment_type']

class PaymentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentType
        fields = ['id', 'name', 'is_disabled']

class PaymentMethodCreateSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(queryset=Peer.objects.all())
    payment_type = serializers.PrimaryKeyRelatedField(queryset=PaymentType.objects.all())
    class Meta:
        model = PaymentMethod
        fields = [
            'id',
            'payment_type',
            'owner',
            'account_name',
            'account_number'
        ]

    def create(self, validated_data):
        owner_wallet_hash = validated_data['owner'].wallet_hash
        payment_type_id = validated_data['payment_type'].id

        if PaymentMethod.objects.filter(owner__wallet_hash=owner_wallet_hash, payment_type__id=payment_type_id).exists():
            raise serializers.ValidationError('A record with the same payment_type already exists for this user')

class PaymentMethodSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(queryset=Peer.objects.all())
    payment_type = PaymentTypeSerializer()
    class Meta:
        model = PaymentMethod
        fields = [
            'id',
            'payment_type',
            'owner',
            'account_name',
            'account_number'
        ]

class PaymentMethodUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentMethod
        fields = [
            'account_name',
            'account_number'
        ]