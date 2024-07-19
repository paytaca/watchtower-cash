from rest_framework import serializers
import rampp2p.models as models
from django.db.models import Q

import logging
logger = logging.getLogger(__name__)

class PaymentTypeFieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.PaymentTypeField
        fields = [
            'id',
            'fieldname',
            'format',
            'description',
            'payment_type',
            'required'
        ]

class PaymentTypeSerializer(serializers.ModelSerializer):
    fields = PaymentTypeFieldSerializer(many=True)
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
            'acc_name_required',
            'fields'
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
    # identifier_format = serializers.PrimaryKeyRelatedField(queryset=models.IdentifierFormat.objects.all())
    class Meta:
        model = models.PaymentMethod
        fields = [
            'id',
            'payment_type',
            'owner',
        ]

    def create(self, validated_data):
        owner_wallet_hash = validated_data['owner'].wallet_hash
        payment_type_id = validated_data['payment_type'].id

        # returns an error if a record with the same payment type already exist for the user
        if models.PaymentMethod.objects.filter(owner__wallet_hash=owner_wallet_hash, payment_type__id=payment_type_id).exists():
            raise serializers.ValidationError('A record with the same payment_type already exists for this user')
        
        instance, _ = models.PaymentMethod.objects.get_or_create(**validated_data)
        return instance
    
class PaymentMethodFieldSerializer(serializers.ModelSerializer):
    field_reference = PaymentTypeFieldSerializer(read_only=True)
    class Meta:
        model = models.PaymentMethodField
        fields = [
            'payment_method',
            'field_reference',
            'value',
            'created_at',
            'modified_at'
        ]

class PaymentMethodSerializer(serializers.ModelSerializer):
    payment_type = PaymentTypeSerializer(read_only=True)
    values = PaymentMethodFieldSerializer(many=True, read_only=True)
    class Meta:
        model = models.PaymentMethod
        fields = [
            'id',
            'payment_type',
            'owner',
            'values'
        ]

    def create(self, validated_data):
        payment_type_id = validated_data.pop('payment_type')
        existing_payment_type = models.PaymentType.objects.get(id=payment_type_id)

        # Create a new PaymentMethod instance
        payment_method = models.PaymentMethod.objects.create(
            payment_type=existing_payment_type,
            owner=validated_data['owner'],
        )

        return payment_method

class PaymentMethodUpdateSerializer(serializers.ModelSerializer):
    identifier_format = serializers.PrimaryKeyRelatedField(queryset=models.IdentifierFormat.objects.all())
    class Meta:
        model = models.PaymentMethod
        fields = [
            'account_name',
            'account_identifier',
            'identifier_format'
        ]