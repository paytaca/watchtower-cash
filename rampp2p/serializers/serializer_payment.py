from rest_framework import serializers
import rampp2p.models as models

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
    class Meta:
        model = models.PaymentType
        fields = [
            'id',
            'full_name',
            'short_name',
            'notes',
            'is_disabled',
            'fields'
        ]

class SubsetPaymentMethodSerializer(serializers.ModelSerializer):
    payment_type = serializers.SlugRelatedField(slug_field="short_name", queryset=models.PaymentType.objects.all())
    values = serializers.SerializerMethodField()
    dynamic_values = serializers.SerializerMethodField()

    class Meta:
        model = models.PaymentMethod
        fields = [
            'id',
            'payment_type',
            'values',
            'dynamic_values'
        ]
    
    def get_values(self, obj):
        payment_method_fields = models.PaymentMethodField.objects.filter(payment_method=obj.id)
        return PaymentMethodFieldSerializer(payment_method_fields, many=True).data

    def get_dynamic_values(self, obj):
        dynamic_fields = obj.payment_type.dynamic_fields.all()
        serialized_data = DynamicPaymentTypeFieldSerializer(dynamic_fields, many=True)
        return serialized_data.data

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

class DynamicPaymentTypeFieldSerializer(serializers.ModelSerializer):
    fieldname = serializers.CharField()
    model_ref = serializers.CharField()
    field_ref = serializers.CharField()
    payment_type = serializers.PrimaryKeyRelatedField(queryset=models.PaymentType.objects.all())

    class Meta:
        model = models.PaymentMethodField
        fields = [
            'id',
            'fieldname',
            'model_ref',
            'field_ref',
            'payment_type'
        ]
    
class PaymentMethodFieldSerializer(serializers.ModelSerializer):
    field_reference = PaymentTypeFieldSerializer(read_only=True)
    class Meta:
        model = models.PaymentMethodField
        fields = [
            'id',
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