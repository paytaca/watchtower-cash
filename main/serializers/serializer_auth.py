from rest_framework import serializers
from django.contrib.auth.models import User

class SignInSerializer(serializers.Serializer):
    username = serializers.CharField(read_only=True)
    password = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ['username','password']

class SignUpSerializer(serializers.Serializer):
    email = serializers.CharField(read_only=True)
    first_name = serializers.CharField(read_only=True)
    last_name = serializers.CharField(read_only=True)
    
    class Meta:
        model = User
        

class SignOutSerializer(serializers.Serializer):
    class Meta:
        model = User
        fields = ['username','id']
    
    

