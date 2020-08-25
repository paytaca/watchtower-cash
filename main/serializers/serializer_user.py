import functools
import logging
from rest_framework import serializers, exceptions
from django.db.models.fields import EmailField
from django.contrib.auth.models import User
logger = logging.getLogger(__name__)


class CreateAccountSerializer(serializers.Serializer):
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    email = serializers.EmailField()
    username = serializers.FloatField()
    password = serializers.CharField()
    action =  serializers.CharField(default='register')


    def create(self, validated_data):
        return User.objects.create(**validated_data)


    def update(self, instance, validated_data):
        instance.first_name = validated_data.get('first_name', instance.first_name)
        instance.last_name = validated_data.get('last_name', instance.last_name)
        instance.email = validated_data.get('email', instance.email)
        instance.username = validated_data.get('username', instance.username)
        instance.save()


    def process(self):
        pass
        # action = self.data['action']
        # status = 'failed'
        # if action == 'register':
        #     firstname = request.POST['firstname']

        #     lastname = request.POST['lastname']
        #     email = request.POST['email']
        #     password = request.POST['password']
        #     username = request.POST['username']

        #     # Create User
        #     user = User()
        #     user.username = username
        #     user.first_name = firstname
        #     user.last_name = lastname
        #     user.email = email
        #     user.save()
        #     user.set_password(password)
        #     user.save()

        #     # Create Subscriber
        #     subscriber = Subscriber()
        #     subscriber.user = user
        #     subscriber.save()
        #     status = 'success'
        #     return redirect('home')
            
        # if action == 'update':
        #     return redirect('account')


class PasswordSerializer(serializers.Serializer):
    pass

class UserSerializer(serializers.ModelSerializer):
    model = User
    fields = [
        'txid',
        'address',
        'amount',
        'acknowledge',
        'blockheight',
        'source',
        'created_datetime',
        'token',
        'scanning',
        'subscribed',
        'spentIndex',
    ]






    




    




