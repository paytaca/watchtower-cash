from rest_framework import serializers
from ..base_models import Appeal

class AppealSerializer(serializers.ModelSerializer):
    class Meta:
        model = Appeal
        fields = [
           'id',
           'type',
           'creator',
           'order',
           'created_at'
        ]