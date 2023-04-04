from rest_framework import serializers
from ..models.payment import PaymentMethod, PaymentType
from ..models.peer import Peer

class PaymentTypeSerializer(serializers.ModelSerializer):
  class Meta:
    model = PaymentType
    fields = ['id', 'name', 'is_disabled']

class PaymentMethodSerializer(serializers.ModelSerializer):
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
    depth = 1