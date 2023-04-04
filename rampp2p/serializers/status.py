from rest_framework import serializers
from ..models.status import Status

class StatusSerializer(serializers.ModelSerializer):
  class Meta:
    model = Status
    fields = [
      'id',
      'status',
      'order',
      'created_at'
    ]