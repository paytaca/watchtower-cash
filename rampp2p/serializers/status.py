from rest_framework import serializers
from rampp2p.models import (
    Status,
    Order
)

class StatusSerializer(serializers.ModelSerializer):
  order = serializers.PrimaryKeyRelatedField(queryset=Order.objects.all())
  status = serializers.CharField()
  class Meta:
    model = Status
    fields = [
      'id',
      'status',
      'order',
      'created_at'
    ]