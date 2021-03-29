from django.contrib.auth import authenticate
from rest_framework import serializers
from django.contrib.auth import get_user_model


def get_and_authenticate_user(username, password):
    user = authenticate(username=username, password=password)
    if user is None:
        raise serializers.ValidationError("Invalid username/password. Please try again!")
    return user

def create_user_account(email, password, username, first_name="", last_name="", **extra_fields):
    user = get_user_model().objects.create_user(
        email=email,
        password=password,
        username=username,
        first_name=first_name,
        last_name=last_name,
        **extra_fields)
    # subscriber = Subscriber()
    # subscriber.user = user
    # subscriber.confirmed = True
    # subscriber.save()
    return user