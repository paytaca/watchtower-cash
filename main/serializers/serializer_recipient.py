from main.models import Recipient
from rest_framework import serializers, exceptions

class RecipientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Recipient
        fields = ['web_url',]    