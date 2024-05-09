from rest_framework import serializers
import rampp2p.models as models
from django.db.models import Q

import logging
logger = logging.getLogger(__name__)

class PaymentTypeSerializer(serializers.ModelSerializer):
    formats = serializers.SlugRelatedField(slug_field="format", queryset=models.IdentifierFormat.objects.all(), many=True)
    class Meta:
        model = models.PaymentType
        fields = [
            'id',
            'full_name',
            'short_name',
            'formats',
            'notes',
            'is_disabled',
            'acc_name_required'
        ]

class SubsetPaymentMethodSerializer(serializers.ModelSerializer):
    payment_type = serializers.SlugRelatedField(slug_field="short_name", queryset=models.PaymentType.objects.all())
    identifier_format = serializers.SlugRelatedField(slug_field="format", queryset=models.IdentifierFormat.objects.all())
    class Meta:
        model = models.PaymentMethod
        fields = [
            'id',
            'payment_type',
            'account_name',
            'account_identifier',
            'identifier_format'
        ]

class RelatedPaymentMethodSerializer(serializers.ModelSerializer):
    payment_type = serializers.SerializerMethodField()
    class Meta:
        model = models.PaymentMethod
        fields = ['id', 'payment_type']

    def get_payment_type(self, obj):
        name = obj.payment_type.short_name
        if name == '':
            name = obj.payment_type.full_name
        return {
            'id': obj.payment_type.id,
            'name': name
        }

class PaymentMethodCreateSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(queryset=models.Peer.objects.all())
    payment_type = serializers.PrimaryKeyRelatedField(queryset=models.PaymentType.objects.all())
    identifier_format = serializers.PrimaryKeyRelatedField(queryset=models.IdentifierFormat.objects.all())
    class Meta:
        model = models.PaymentMethod
        fields = [
            'id',
            'payment_type',
            'owner',
            'account_name',
            'account_identifier',
            'identifier_format'
        ]

    def create(self, validated_data):
        owner_wallet_hash = validated_data['owner'].wallet_hash
        payment_type_id = validated_data['payment_type'].id

        # returns an error if a record with the same payment type already exist for the user
        if models.PaymentMethod.objects.filter(owner__wallet_hash=owner_wallet_hash, payment_type__id=payment_type_id).exists():
            raise serializers.ValidationError('A record with the same payment_type already exists for this user')
        
        instance, _ = models.PaymentMethod.objects.get_or_create(**validated_data)
        return instance

class PaymentMethodSerializer(serializers.ModelSerializer):
    payment_type = PaymentTypeSerializer()
    owner = serializers.PrimaryKeyRelatedField(queryset=models.Peer.objects.all())
    identifier_format = serializers.SlugRelatedField(slug_field="format", queryset=models.IdentifierFormat.objects.all())
    class Meta:
        model = models.PaymentMethod
        fields = [
            'id',
            'payment_type',
            'owner',
            'account_name',
            'account_identifier',
            'identifier_format'
        ]

class PaymentMethodUpdateSerializer(serializers.ModelSerializer):
    identifier_format = serializers.PrimaryKeyRelatedField(queryset=models.IdentifierFormat.objects.all())
    class Meta:
        model = models.PaymentMethod
        fields = [
            'account_name',
            'account_identifier',
            'identifier_format'
        ]