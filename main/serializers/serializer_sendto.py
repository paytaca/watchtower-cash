from main.models import SendTo
from rest_framework import serializers, exceptions

class SendToSerializer(serializers.ModelSerializer):
    class Meta:
        model = SendTo
        fields = ['address',]    